from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from core.database import get_db
from core.security import get_current_user, require_admin
from models.note import Note, Folder
from models.user import User

router = APIRouter(prefix="/api/notes", tags=["notes"])

# ── Schemas ───────────────────────────────────────────────────────

class CreateFolderRequest(BaseModel):
    name:      str
    parent_id: Optional[int] = None

class CreateNoteRequest(BaseModel):
    title:     str
    content:   Optional[str] = ""
    folder_id: Optional[int] = None
    tags:      Optional[str] = ""

class UpdateNoteRequest(BaseModel):
    title:     Optional[str] = None
    content:   Optional[str] = None
    folder_id: Optional[int] = None
    tags:      Optional[str] = None

# ── Folder routes ─────────────────────────────────────────────────

@router.get("/folders")
def list_folders(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    folders = db.query(Folder).all()
    return [f.to_dict() for f in folders]

@router.post("/folders", status_code=201)
def create_folder(
    payload: CreateFolderRequest,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin)
):
    folder = Folder(
        name       = payload.name,
        parent_id  = payload.parent_id,
        created_by = admin.id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder.to_dict()

@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db:        Session = Depends(get_db),
    admin:     User    = Depends(require_admin)
):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Move notes in this folder to root
    db.query(Note).filter(Note.folder_id == folder_id).update({"folder_id": None})
    db.delete(folder)
    db.commit()
    return {"message": "Folder deleted, notes moved to root"}

# ── Note routes ───────────────────────────────────────────────────

@router.get("/")
def list_notes(
    folder_id: Optional[int] = None,
    db:        Session = Depends(get_db),
    _:         User    = Depends(get_current_user)
):
    query = db.query(Note)
    if folder_id is not None:
        query = query.filter(Note.folder_id == folder_id)
    notes = query.order_by(Note.updated_at.desc().nullslast(), Note.created_at.desc()).all()
    # Return without full content for listing
    result = []
    for n in notes:
        d = n.to_dict()
        d["content"] = d["content"][:200] + "..." if len(d["content"]) > 200 else d["content"]
        result.append(d)
    return result

@router.post("/", status_code=201)
def create_note(
    payload: CreateNoteRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    note = Note(
        title         = payload.title,
        content       = payload.content,
        folder_id     = payload.folder_id,
        author_id     = current.id,
        author_handle = current.handle,
        tags          = payload.tags,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note.to_dict()

@router.get("/{note_id}")
def get_note(
    note_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user)
):
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note.to_dict()

@router.patch("/{note_id}")
def update_note(
    note_id: int,
    payload: UpdateNoteRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.author_id != current.id and not current.is_admin:
        raise HTTPException(status_code=403, detail="You can only edit your own notes")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return note.to_dict()

@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can delete notes")
    db.delete(note)
    db.commit()
    return {"message": "Note deleted"}
