from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field
from typing import Optional
from core.database import get_db
from core.security import hash_password, get_current_user, require_admin
from core.validation import clean_text, reject_html
from models.user import User, RANKS
from models.ioc import IOC
from models.vault import VaultFile
from models.note import Folder, Note
from models.bookmark import Bookmark
from models.achievement import UserAchievement, UserSpecialization
from models.ctf import CTFParticipant, CTFParticipationMarker
from fastapi import UploadFile, File
import uuid, os, re
from core.config import MASTER_HANDLE
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "profile_uploads"))
os.makedirs(f"{UPLOAD_DIR}/avatars", exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/banners", exist_ok=True)

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
ALLOWED_IMAGE_EXT  = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
HANDLE_RE          = re.compile(r'^[a-zA-Z0-9_]{2,50}$')
MAX_IMAGE_SIZE     = 5 * 1024 * 1024
EXT_EQUIV          = {".jpeg": ".jpg"}
PROFILE_STATUSES   = {"available", "busy", "ctf", "pwnbox"}

router = APIRouter(prefix="/api/users", tags=["users"])

# ── Schemas ───────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    handle:   str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    emoji:    Optional[str]  = Field(default="🐱", max_length=10)
    bio:      Optional[str]  = Field(default="", max_length=2000)
    rank:     Optional[str]  = Field(default="DEADCAT", max_length=20)
    is_admin: Optional[bool] = False

class UpdateUserRequest(BaseModel):
    bio:      Optional[str] = Field(default=None, max_length=2000)
    emoji:    Optional[str] = Field(default=None, max_length=10)
    rank:     Optional[str] = Field(default=None, max_length=20)
    github:   Optional[str] = Field(default=None, max_length=100)
    twitter:  Optional[str] = Field(default=None, max_length=100)
    htb:      Optional[str] = Field(default=None, max_length=100)
    ctftime:  Optional[str] = Field(default=None, max_length=100)
    profile_status: Optional[str] = Field(default=None, max_length=40)
    is_active:Optional[bool]= None
    is_admin: Optional[bool]= None
    title:    Optional[str] = Field(default=None, max_length=100)

class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


def _detect_image_ext(header: bytes) -> Optional[str]:
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    return None


def _canonical_ext(ext: str) -> str:
    return EXT_EQUIV.get(ext, ext)


def _save_bounded_upload(file: UploadFile, path: str, max_size: int) -> bytes:
    total = 0
    head = b""
    with open(path, "wb") as out:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size:
                out.close()
                os.remove(path)
                raise HTTPException(status_code=413, detail=f"Image too large (max {max_size // (1024 * 1024)}MB)")
            if len(head) < 32:
                head += chunk[:32 - len(head)]
            out.write(chunk)
    return head


def _get_ctf_stats_for_handle(db: Session, handle: str) -> dict:
    totals = (
        db.query(
            CTFParticipant.member_handle.label("member_handle"),
            func.coalesce(func.sum(CTFParticipant.points), 0.0).label("total_points"),
        )
        .group_by(CTFParticipant.member_handle)
        .subquery()
    )
    row = db.query(totals.c.total_points).filter(totals.c.member_handle == handle).first()
    if not row:
        return {"points": 0.0, "rank": None}
    points = float(row.total_points or 0.0)
    higher_count = db.query(func.count()).select_from(totals).filter(totals.c.total_points > points).scalar() or 0
    return {"points": points, "rank": int(higher_count) + 1}

# ── Routes ────────────────────────────────────────────────────────

@router.get("/")
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)   # any logged-in user can see the list
):
    """List all active members."""
    users = db.query(User).filter(User.is_active == True).all()
    return [u.to_dict() for u in users]


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin)   # admin only
):
    """Admin creates a new member account."""
    handle = reject_html(clean_text(payload.handle, field="Handle", max_len=50), field="Handle")
    password = clean_text(payload.password, field="Password", max_len=128, strip=False)
    if not HANDLE_RE.match(handle):
        raise HTTPException(status_code=400, detail="Handle must be 2–50 characters, letters/numbers/underscores only.")
    if handle == MASTER_HANDLE:
        raise HTTPException(status_code=400, detail="Handle not available")
    if db.query(User).filter(User.handle == handle).first():
        raise HTTPException(status_code=409, detail="Handle already taken")

    if payload.rank not in RANKS:
        raise HTTPException(status_code=400, detail=f"Invalid rank. Choose from: {RANKS}")

    user = User(
        handle   = handle,
        password = hash_password(password),
        emoji    = clean_text(payload.emoji, field="Emoji", max_len=10),
        bio      = clean_text(payload.bio, field="Bio", max_len=2000),
        rank     = payload.rank,
        is_admin = payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    from core.logger import log_admin
    log_admin(admin.handle, "create_user", user.handle, f"rank={user.rank}, admin={user.is_admin}")
    return user.to_dict(include_private=admin.is_admin)


@router.get("/{handle}")
def get_user(
    handle: str,
    db:     Session = Depends(get_db),
    _:      User    = Depends(get_current_user)
):
    """Get a member's public profile."""
    user = db.query(User).filter(User.handle == handle).first()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")
    data = user.to_dict()
    data["ctf_stats"] = _get_ctf_stats_for_handle(db, user.handle)
    return data


@router.patch("/{handle}")
def update_user(
    handle:  str,
    payload: UpdateUserRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    """
    Update a member's profile.
    - Members can update their own bio, emoji, and social links.
    - Only admins can change rank, is_active, or is_admin.
    """
    user = db.query(User).filter(User.handle == handle).first()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")

    # Non-admins can only edit their own profile
    if not current.is_admin and current.handle != handle:
        raise HTTPException(status_code=403, detail="Cannot edit another member's profile")

    # Availability/status is strictly self-only, even for admins.
    if payload.profile_status is not None and current.handle != handle:
        raise HTTPException(status_code=403, detail="Profile status can only be changed by the profile owner")

    # Only master can edit other admins
    if user.is_admin and current.handle != MASTER_HANDLE and current.handle != handle:
        raise HTTPException(status_code=403, detail="Only the master account can modify admin accounts")
    # Admin-only fields
    if not current.is_admin:
        if payload.rank is not None or payload.is_active is not None or payload.is_admin is not None:
            raise HTTPException(status_code=403, detail="Only admins can change rank or account status")

    # Apply updates
    for field, value in payload.model_dump(exclude_none=True).items():
        if field == "rank" and value not in RANKS:
            raise HTTPException(status_code=400, detail=f"Invalid rank. Choose from: {RANKS}")
        if field == "profile_status":
            value = clean_text(value, field=field, max_len=40).strip().lower()
            if value not in PROFILE_STATUSES:
                raise HTTPException(status_code=400, detail=f"Invalid profile_status. Choose from: {sorted(PROFILE_STATUSES)}")
        if field in {"github", "twitter", "htb", "ctftime", "title", "emoji", "rank"}:
            value = reject_html(clean_text(value, field=field, max_len=100 if field != "emoji" else 10), field=field)
        if field == "bio":
            value = clean_text(value, field=field, max_len=2000)
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user.to_dict(include_private=current.is_admin)


@router.post("/{handle}/reset-password")
def reset_password(
    handle:  str,
    payload: ChangePasswordRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    """
    Change password.
    - Members can change their own password.
    - Admins can reset anyone's password.
    """
    user = db.query(User).filter(User.handle == handle).first()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")

    if not current.is_admin and current.handle != handle:
        raise HTTPException(status_code=403, detail="Cannot change another member's password")
    
    # Only master can reset another admin's password
    if user.is_admin and current.handle != MASTER_HANDLE and current.handle != handle:
        raise HTTPException(status_code=403, detail="Only the master account can reset an admin's password")	
    user.password = hash_password(clean_text(payload.new_password, field="Password", max_len=128, strip=False))
    db.commit()
    return {"message": "Password updated successfully"}

@router.post("/{handle}/avatar")
async def upload_avatar(
    handle:  str,
    file:    UploadFile = File(...),
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    if current.handle != handle and not current.is_admin:
        raise HTTPException(403, "Cannot edit another member's profile")
    user = db.query(User).filter(User.handle == handle).first()
    if not user: raise HTTPException(404, "Member not found")
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    ext  = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT or (file.content_type and file.content_type not in ALLOWED_IMAGE_MIME):
        raise HTTPException(400, "Invalid image type")
    fname = f"{uuid.uuid4().hex}{ext}"
    path  = f"{UPLOAD_DIR}/avatars/{fname}"
    header = _save_bounded_upload(file, path, MAX_IMAGE_SIZE)
    detected = _detect_image_ext(header)
    if not detected or _canonical_ext(ext) != _canonical_ext(detected):
        os.remove(path)
        raise HTTPException(400, "Invalid image content")
    user.avatar_url = f"/profile_uploads/avatars/{fname}"
    db.commit()
    db.refresh(user)
    return {"avatar_url": user.avatar_url}

@router.post("/{handle}/banner")
async def upload_banner(
    handle:  str,
    file:    UploadFile = File(...),
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    if current.handle != handle and not current.is_admin:
        raise HTTPException(403, "Cannot edit another member's profile")
    user = db.query(User).filter(User.handle == handle).first()
    if not user: raise HTTPException(404, "Member not found")
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    ext  = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT or (file.content_type and file.content_type not in ALLOWED_IMAGE_MIME):
        raise HTTPException(400, "Invalid image type")
    fname = f"{uuid.uuid4().hex}{ext}"
    path  = f"{UPLOAD_DIR}/banners/{fname}"
    header = _save_bounded_upload(file, path, MAX_IMAGE_SIZE)
    detected = _detect_image_ext(header)
    if not detected or _canonical_ext(ext) != _canonical_ext(detected):
        os.remove(path)
        raise HTTPException(400, "Invalid image content")
    user.banner_url = f"/profile_uploads/banners/{fname}"
    db.commit()
    db.refresh(user)
    return {"banner_url": user.banner_url}

@router.delete("/{handle}")
def delete_user(
    handle: str,
    db:     Session = Depends(get_db),
    admin:  User    = Depends(require_admin)
):
    """Admin permanently deletes a member account."""
    user = db.query(User).filter(User.handle == handle).first()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")
    if user.handle == admin.handle:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    # Only master can delete other admins
    if user.is_admin and admin.handle != MASTER_HANDLE:
        raise HTTPException(status_code=403, detail="Only the master account can delete admin accounts")

    # Keep authored content but remove FK ties to deleted user.
    db.query(IOC).filter(IOC.author_id == user.id).update({"author_id": None}, synchronize_session=False)
    db.query(VaultFile).filter(VaultFile.author_id == user.id).update({"author_id": None}, synchronize_session=False)
    db.query(Note).filter(Note.author_id == user.id).update({"author_id": None}, synchronize_session=False)
    db.query(Folder).filter(Folder.created_by == user.id).update({"created_by": None}, synchronize_session=False)

    # Remove user-owned relational records.
    db.query(Bookmark).filter(Bookmark.user_id == user.id).delete(synchronize_session=False)
    db.query(UserAchievement).filter(UserAchievement.user_id == user.id).delete(synchronize_session=False)
    db.query(UserSpecialization).filter(UserSpecialization.user_id == user.id).delete(synchronize_session=False)
    db.query(CTFParticipationMarker).filter(CTFParticipationMarker.user_id == user.id).delete(synchronize_session=False)

    db.delete(user)
    db.commit()
    from core.logger import log_admin
    log_admin(admin.handle, "delete_user", handle, "permanent")
    return {"message": f"{handle} has been deleted"}
