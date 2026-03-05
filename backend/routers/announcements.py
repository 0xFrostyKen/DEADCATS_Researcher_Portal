from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta, timezone
from core.database import get_db
from core.security import get_current_user, require_admin
from core.validation import clean_text, reject_html
from models.announcement import Announcement
from models.user import User

router = APIRouter(prefix="/api/announcements", tags=["announcements"])

class CreateAnnouncementRequest(BaseModel):
    title:      str = Field(min_length=1, max_length=200)
    content:    Optional[str] = Field(default="", max_length=4000)
    type:       Optional[str] = Field(default="notice", max_length=20)  # notice | creds
    expires_in: Optional[int] = 1  # days: 1 | 2 | 3
    pinned:     Optional[bool] = False

@router.get("/")
def list_announcements(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user)
):
    now = datetime.now(timezone.utc)
    announcements = db.query(Announcement).filter(
        (Announcement.expires_at == None) | (Announcement.expires_at > now)
    ).order_by(Announcement.pinned.desc(), Announcement.created_at.desc()).all()
    return [a.to_dict() for a in announcements]

@router.post("/", status_code=201)
def create_announcement(
    payload: CreateAnnouncementRequest,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin)
):
    ann_type = clean_text(payload.type, field="type", max_len=20)
    if ann_type not in {"notice", "creds"}:
        raise HTTPException(400, "Invalid announcement type")
    if payload.expires_in is None or payload.expires_in not in {1, 2, 3}:
        raise HTTPException(400, "expires_in must be one of: 1, 2, 3")
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in)
    a = Announcement(
        title      = reject_html(clean_text(payload.title, field="title", max_len=200), field="title"),
        content    = clean_text(payload.content, field="content", max_len=4000),
        type       = ann_type,
        author     = admin.handle,
        expires_at = expires_at,
        pinned     = payload.pinned,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a.to_dict()

@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    db:              Session = Depends(get_db),
    _:               User    = Depends(require_admin)
):
    a = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not a:
        raise HTTPException(404, "Not found")
    db.delete(a); db.commit()
    return {"message": "Deleted"}
