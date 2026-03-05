from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from core.database import get_db
from core.security import get_current_user, require_admin
from core.validation import clean_text, reject_html
from models.achievement import Achievement, UserAchievement, UserSpecialization
from models.user import User, RANKS

router = APIRouter(prefix="/api/achievements", tags=["achievements"])

# ── Schemas ───────────────────────────────────────────────────────

class CreateAchievementRequest(BaseModel):
    icon:   str = Field(min_length=1, max_length=10)
    name:   str = Field(min_length=1, max_length=100)
    desc:   Optional[str] = Field(default="", max_length=500)
    rarity: Optional[str] = Field(default="common", max_length=20)

class AssignAchievementRequest(BaseModel):
    achievement_id: int
    equipped:       Optional[bool] = False

class EquipAchievementRequest(BaseModel):
    achievement_id: int

class CreateSpecRequest(BaseModel):
    icon:  Optional[str] = Field(default="🔧", max_length=10)
    name:  str = Field(min_length=1, max_length=100)
    level: Optional[str] = Field(default="NOVICE", max_length=30)

class UpdateUserRequest(BaseModel):
    bio:     Optional[str] = Field(default=None, max_length=2000)
    emoji:   Optional[str] = Field(default=None, max_length=10)
    rank:    Optional[str] = Field(default=None, max_length=20)
    github:  Optional[str] = Field(default=None, max_length=100)
    twitter: Optional[str] = Field(default=None, max_length=100)
    htb:     Optional[str] = Field(default=None, max_length=100)
    ctftime: Optional[str] = Field(default=None, max_length=100)

# ── Global achievements (admin manages) ──────────────────────────

@router.get("/")
def list_achievements(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user)
):
    return [a.to_dict() for a in db.query(Achievement).all()]

@router.post("/", status_code=201)
def create_achievement(
    payload: CreateAchievementRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(require_admin)
):
    a = Achievement(
        icon=clean_text(payload.icon, field="icon", max_len=10),
        name=reject_html(clean_text(payload.name, field="name", max_len=100), field="name"),
        desc=clean_text(payload.desc, field="desc", max_len=500),
        rarity=clean_text(payload.rarity, field="rarity", max_len=20),
    )
    db.add(a); db.commit(); db.refresh(a)
    # Auto-unlock for creator so it appears on their profile immediately.
    db.add(UserAchievement(user_id=current.id, achievement_id=a.id, equipped=False))
    db.commit()
    return a.to_dict()

@router.delete("/{achievement_id}")
def delete_achievement(
    achievement_id: int,
    db: Session = Depends(get_db),
    _:  User    = Depends(require_admin)
):
    a = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not a:
        raise HTTPException(404, "Achievement not found")
    db.delete(a); db.commit()
    return {"message": "Deleted"}

# ── User achievements ─────────────────────────────────────────────

@router.get("/user/{user_id}")
def get_user_achievements(
    user_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user)
):
    uas = db.query(UserAchievement).filter(UserAchievement.user_id == user_id).all()
    result = []
    for ua in uas:
        a = db.query(Achievement).filter(Achievement.id == ua.achievement_id).first()
        if a:
            result.append({
                **a.to_dict(),
                "unlocked":    ua.unlocked,
                "equipped":    ua.equipped,
                "unlocked_at": str(ua.unlocked_at),
            })
    return result

@router.post("/user/{user_id}/assign")
def assign_achievement(
    user_id: int,
    payload: AssignAchievementRequest,
    db:      Session = Depends(get_db),
    _:       User    = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    achievement = db.query(Achievement).filter(Achievement.id == payload.achievement_id).first()
    if not achievement:
        raise HTTPException(404, "Achievement not found")
    # Check not already assigned
    exists = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id,
        UserAchievement.achievement_id == payload.achievement_id
    ).first()
    if exists:
        raise HTTPException(400, "Achievement already assigned")
    ua = UserAchievement(
        user_id        = user_id,
        achievement_id = payload.achievement_id,
        equipped       = payload.equipped,
    )
    db.add(ua); db.commit(); db.refresh(ua)
    return ua.to_dict()

@router.delete("/user/{user_id}/revoke/{achievement_id}")
def revoke_achievement(
    user_id:        int,
    achievement_id: int,
    db:             Session = Depends(get_db),
    _:              User    = Depends(require_admin)
):
    ua = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id,
        UserAchievement.achievement_id == achievement_id
    ).first()
    if not ua:
        raise HTTPException(404, "Not found")
    db.delete(ua); db.commit()
    return {"message": "Revoked"}

@router.post("/user/{user_id}/equip")
def equip_achievement(
    user_id: int,
    payload: EquipAchievementRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    # Only self or admin
    if current.id != user_id and not current.is_admin:
        raise HTTPException(403, "Forbidden")
    exists = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id,
        UserAchievement.achievement_id == payload.achievement_id
    ).first()
    if not exists:
        raise HTTPException(404, "Achievement not assigned to user")
    # Unequip all first
    db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id
    ).update({"equipped": False})
    # Equip selected
    exists.equipped = True
    db.commit()
    return {"message": "Equipped"}

# ── Specializations ───────────────────────────────────────────────

@router.get("/user/{user_id}/specs")
def get_specs(
    user_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user)
):
    return [s.to_dict() for s in db.query(UserSpecialization).filter(
        UserSpecialization.user_id == user_id
    ).all()]

@router.post("/user/{user_id}/specs", status_code=201)
def add_spec(
    user_id: int,
    payload: CreateSpecRequest,
    db:      Session = Depends(get_db),
    _:       User    = Depends(require_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    s = UserSpecialization(
        user_id=user_id,
        icon=clean_text(payload.icon, field="icon", max_len=10),
        name=reject_html(clean_text(payload.name, field="name", max_len=100), field="name"),
        level=clean_text(payload.level, field="level", max_len=30),
    )
    db.add(s); db.commit(); db.refresh(s)
    return s.to_dict()

@router.delete("/user/{user_id}/specs/{spec_id}")
def delete_spec(
    user_id: int,
    spec_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(require_admin)
):
    s = db.query(UserSpecialization).filter(
        UserSpecialization.id == spec_id,
        UserSpecialization.user_id == user_id
    ).first()
    if not s:
        raise HTTPException(404, "Not found")
    db.delete(s); db.commit()
    return {"message": "Deleted"}

# ── Profile update (self or admin) ────────────────────────────────

@router.patch("/user/{user_id}/profile")
def update_profile(
    user_id: int,
    payload: UpdateUserRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    if current.id != user_id and not current.is_admin:
        raise HTTPException(403, "Forbidden")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    # Only admins can change rank
    data = payload.model_dump(exclude_none=True)
    if "rank" in data and not current.is_admin:
        del data["rank"]
    if data.get("rank") and data["rank"] not in RANKS:
        raise HTTPException(400, f"Invalid rank. Choose from: {RANKS}")
    for field, value in data.items():
        if field in {"github", "twitter", "htb", "ctftime", "emoji", "rank"}:
            value = reject_html(clean_text(value, field=field, max_len=100 if field != "emoji" else 10), field=field)
        if field == "bio":
            value = clean_text(value, field=field, max_len=2000)
        setattr(user, field, value)
    db.commit(); db.refresh(user)
    return user.to_dict()
