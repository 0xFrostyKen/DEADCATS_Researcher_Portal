from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.bookmark import Bookmark
from models.note import Note
from models.ioc import IOC

router = APIRouter(prefix="/api/bookmarks", tags=["bookmarks"])

VALID_TYPES = {"note", "ioc"}


class BookmarkRequest(BaseModel):
    item_type: str
    item_id:   int


@router.get("/")
def list_bookmarks(
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user),
):
    """Return the current user's bookmarks, enriched with the actual note/IOC data."""
    bookmarks = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == current.id)
        .order_by(Bookmark.created_at.desc())
        .all()
    )

    result = []
    for bm in bookmarks:
        entry = bm.to_dict()
        if bm.item_type == "note":
            item = db.query(Note).filter(Note.id == bm.item_id).first()
            entry["data"] = item.to_dict() if item else None
        elif bm.item_type == "ioc":
            item = db.query(IOC).filter(IOC.id == bm.item_id).first()
            entry["data"] = item.to_dict() if item else None
        else:
            entry["data"] = None
        result.append(entry)

    return result


@router.post("/", status_code=status.HTTP_201_CREATED)
def add_bookmark(
    payload: BookmarkRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user),
):
    """Bookmark a note or IOC for the current user."""
    if payload.item_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"item_type must be one of: {sorted(VALID_TYPES)}")

    # Verify the referenced item exists
    if payload.item_type == "note":
        if not db.query(Note).filter(Note.id == payload.item_id).first():
            raise HTTPException(status_code=404, detail="Note not found")
    else:
        if not db.query(IOC).filter(IOC.id == payload.item_id).first():
            raise HTTPException(status_code=404, detail="IOC not found")

    # Prevent duplicate bookmark
    existing = db.query(Bookmark).filter(
        Bookmark.user_id   == current.id,
        Bookmark.item_type == payload.item_type,
        Bookmark.item_id   == payload.item_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Already bookmarked")

    bm = Bookmark(
        user_id   = current.id,
        item_type = payload.item_type,
        item_id   = payload.item_id,
    )
    db.add(bm)
    db.commit()
    db.refresh(bm)
    return bm.to_dict()


@router.delete("/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_bookmark(
    bookmark_id: int,
    db:          Session = Depends(get_db),
    current:     User    = Depends(get_current_user),
):
    """Remove a bookmark. Users can only delete their own bookmarks."""
    bm = db.query(Bookmark).filter(Bookmark.id == bookmark_id).first()
    if not bm:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    if bm.user_id != current.id:
        raise HTTPException(status_code=403, detail="Cannot delete another user's bookmark")
    db.delete(bm)
    db.commit()
