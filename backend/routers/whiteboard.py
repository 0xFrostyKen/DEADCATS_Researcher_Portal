import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from core.database import get_db
from core.security import get_current_user, require_admin
from core.validation import clean_text, reject_html
from models.user import User
from models.goal import TeamGoal
from models.whiteboard_config import WhiteboardConfig

router = APIRouter(prefix="/api/whiteboard", tags=["whiteboard"])


# ── Helpers ────────────────────────────────────────────────────────

def _generate_room_url() -> str:
    room_id  = secrets.token_hex(10)          # 20 hex chars
    enc_key  = secrets.token_urlsafe(16)[:22] # 22 base64url chars
    return f"https://excalidraw.com/#room={room_id},{enc_key}"


def _get_or_create_config(db: Session) -> WhiteboardConfig:
    cfg = db.query(WhiteboardConfig).filter(WhiteboardConfig.id == 1).first()
    if not cfg:
        cfg = WhiteboardConfig(id=1, room_url=_generate_room_url())
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ── Whiteboard config ──────────────────────────────────────────────

@router.get("/config")
def get_config(
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user),
):
    """Return the shared Excalidraw room URL (auth required)."""
    cfg = _get_or_create_config(db)
    return {"room_url": cfg.room_url}


@router.post("/config/reset")
def reset_room(
    db:    Session = Depends(get_db),
    admin: User    = Depends(require_admin),
):
    """Generate a new room ID — discards the existing shared canvas."""
    cfg = _get_or_create_config(db)
    cfg.room_url = _generate_room_url()
    db.commit()
    db.refresh(cfg)
    return {"room_url": cfg.room_url}


# ── Team goals ─────────────────────────────────────────────────────

class GoalCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)

class GoalUpdate(BaseModel):
    text:      Optional[str]  = Field(default=None, min_length=1, max_length=500)
    completed: Optional[bool] = None


@router.get("/goals")
def list_goals(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user),
):
    """List all team goals — visible to all members."""
    goals = (
        db.query(TeamGoal)
        .order_by(TeamGoal.completed.asc(), TeamGoal.created_at.asc())
        .all()
    )
    return [g.to_dict() for g in goals]


@router.post("/goals", status_code=201)
def create_goal(
    payload: GoalCreate,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin),
):
    """Create a new team goal (admin only)."""
    text = reject_html(clean_text(payload.text, field="Goal text", max_len=500), field="Goal text")
    if not text:
        raise HTTPException(status_code=400, detail="Goal text cannot be empty.")
    if len(text) > 500:
        raise HTTPException(status_code=400, detail="Goal text too long (max 500 chars).")
    goal = TeamGoal(text=text, created_by=admin.handle)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal.to_dict()


@router.patch("/goals/{goal_id}")
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin),
):
    """Update a goal's text or completion status (admin only)."""
    goal = db.query(TeamGoal).filter(TeamGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    if payload.text is not None:
        text = reject_html(clean_text(payload.text, field="Goal text", max_len=500), field="Goal text")
        if not text:
            raise HTTPException(status_code=400, detail="Goal text cannot be empty.")
        if len(text) > 500:
            raise HTTPException(status_code=400, detail="Goal text too long (max 500 chars).")
        goal.text = text
    if payload.completed is not None:
        goal.completed    = payload.completed
        goal.completed_at = datetime.now(timezone.utc) if payload.completed else None
        goal.completed_by = admin.handle if payload.completed else None
    db.commit()
    db.refresh(goal)
    return goal.to_dict()


@router.delete("/goals/{goal_id}", status_code=204)
def delete_goal(
    goal_id: int,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin),
):
    """Delete a team goal (admin only)."""
    goal = db.query(TeamGoal).filter(TeamGoal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found.")
    db.delete(goal)
    db.commit()
