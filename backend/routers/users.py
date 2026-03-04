from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from core.database import get_db
from core.security import hash_password, get_current_user, require_admin
from models.user import User, RANKS
from fastapi import UploadFile, File
import uuid, os, shutil, re
from core.config import MASTER_HANDLE
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "profile_uploads"))
os.makedirs(f"{UPLOAD_DIR}/avatars", exist_ok=True)
os.makedirs(f"{UPLOAD_DIR}/banners", exist_ok=True)

ALLOWED_IMAGE_MIME = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
ALLOWED_IMAGE_EXT  = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
HANDLE_RE          = re.compile(r'^[a-zA-Z0-9_]{2,50}$')

router = APIRouter(prefix="/api/users", tags=["users"])

# ── Schemas ───────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    handle:   str
    password: str
    emoji:    Optional[str]  = "🐱"
    bio:      Optional[str]  = ""
    rank:     Optional[str]  = "DEADCAT"
    is_admin: Optional[bool] = False

class UpdateUserRequest(BaseModel):
    bio:      Optional[str] = None
    emoji:    Optional[str] = None
    rank:     Optional[str] = None
    github:   Optional[str] = None
    twitter:  Optional[str] = None
    htb:      Optional[str] = None
    ctftime:  Optional[str] = None
    is_active:Optional[bool]= None
    is_admin: Optional[bool]= None
    title:    Optional[str] = None

class ChangePasswordRequest(BaseModel):
    new_password: str

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
    if not HANDLE_RE.match(payload.handle):
        raise HTTPException(status_code=400, detail="Handle must be 2–50 characters, letters/numbers/underscores only.")
    if db.query(User).filter(User.handle == payload.handle).first():
        raise HTTPException(status_code=409, detail="Handle already taken")

    if payload.rank not in RANKS:
        raise HTTPException(status_code=400, detail=f"Invalid rank. Choose from: {RANKS}")

    user = User(
        handle   = payload.handle,
        password = hash_password(payload.password),
        emoji    = payload.emoji,
        bio      = payload.bio,
        rank     = payload.rank,
        is_admin = payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.to_dict(include_private=True)


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
    return user.to_dict()


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
    user.password = hash_password(payload.new_password)
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
    ext  = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT or (file.content_type and file.content_type not in ALLOWED_IMAGE_MIME):
        raise HTTPException(400, "Invalid image type")
    fname = f"{uuid.uuid4().hex}{ext}"
    path  = f"{UPLOAD_DIR}/avatars/{fname}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
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
    ext  = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT or (file.content_type and file.content_type not in ALLOWED_IMAGE_MIME):
        raise HTTPException(400, "Invalid image type")
    fname = f"{uuid.uuid4().hex}{ext}"
    path  = f"{UPLOAD_DIR}/banners/{fname}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
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
    """Admin disables a member account (soft delete)."""
    user = db.query(User).filter(User.handle == handle).first()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")
    if user.handle == admin.handle:
        raise HTTPException(status_code=400, detail="Cannot disable your own account")
    
    # Only master can deactivate other admins
    if user.is_admin and admin.handle != MASTER_HANDLE:
        raise HTTPException(status_code=403, detail="Only the master account can deactivate admin accounts")

    user.is_active = False
    db.commit()
    return {"message": f"{handle} has been disabled"}
