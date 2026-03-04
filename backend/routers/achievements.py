from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from core.database import get_db
from core.security import get_current_user, require_admin
from models.achievement import Achievement, UserAchievement, UserSpecialization
from models.user import User

router = APIRouter(prefix="/api/achievements", tags=["achievements"])

# ── Schemas ───────────────────────────────────────────────────────

class CreateAchievementRequest(BaseModel):
    icon:   str
    name:   str
    desc:   Optional[str] = ""
    rarity: Optional[str] = "common"

class AssignAchievementRequest(BaseModel):
    achievement_id: int
    equipped:       Optional[bool] = False

class EquipAchievementRequest(BaseModel):
    achievement_id: int

class CreateSpecRequest(BaseModel):
    icon:  Optional[str] = "🔧"
    name:  str
    level: Optional[str] = "NOVICE"

class UpdateUserRequest(BaseModel):
    bio:     Optional[str] = None
    emoji:   Optional[str] = None
    rank:    Optional[str] = None
    github:  Optional[str] = None
    twitter: Optional[str] = None
    htb:     Optional[str] = None
    ctftime: Optional[str] = None

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
    _:       User    = Depends(require_admin)
):
    a = Achievement(**payload.model_dump())
    db.add(a); db.commit(); db.refresh(a)
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
    # Unequip all first
    db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id
    ).update({"equipped": False})
    # Equip selected
    ua = db.query(UserAchievement).filter(
        UserAchievement.user_id == user_id,
        UserAchievement.achievement_id == payload.achievement_id
    ).first()
    if not ua:
        raise HTTPException(404, "Achievement not assigned to user")
    ua.equipped = True
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
    s = UserSpecialization(user_id=user_id, **payload.model_dump())
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
    for field, value in data.items():
        setattr(user, field, value)
    db.commit(); db.refresh(user)
    return user.to_dict()

