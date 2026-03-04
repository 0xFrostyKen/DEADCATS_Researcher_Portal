from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import hashlib, uuid, os
from core.database import get_db
from core.security import get_current_user, require_admin
from models.vault import VaultFile
from models.user import User

router  = APIRouter(prefix="/api/vault", tags=["vault"])
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vault_files"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("/")
def list_files(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user)
):
    files = db.query(VaultFile).order_by(VaultFile.created_at.desc()).all()
    return [f.to_dict() for f in files]

@router.post("/upload", status_code=201)
async def upload_file(
    file:        UploadFile = File(...),
    tags:        Optional[str] = Form(""),
    description: Optional[str] = Form(""),
    db:          Session = Depends(get_db),
    current:     User    = Depends(get_current_user)
):
    content  = await file.read()
    sha256   = hashlib.sha256(content).hexdigest()
    ext      = os.path.splitext(file.filename)[1]
    stored   = f"{uuid.uuid4().hex}{ext}"
    path     = os.path.join(UPLOAD_DIR, stored)

    with open(path, "wb") as f:
        f.write(content)

    vf = VaultFile(
        filename      = stored,
        original_name = file.filename,
        mimetype      = file.content_type or "application/octet-stream",
        size          = len(content),
        sha256        = sha256,
        tags          = tags,
        description   = description,
        author        = current.handle,
        author_id     = current.id,
    )
    db.add(vf); db.commit(); db.refresh(vf)
    return vf.to_dict()

@router.get("/download/{file_id}")
def download_file(
    file_id: int,
    db:      Session = Depends(get_db),
    _:       User    = Depends(get_current_user)
):
    vf = db.query(VaultFile).filter(VaultFile.id == file_id).first()
    if not vf:
        raise HTTPException(404, "File not found")
    path = os.path.join(UPLOAD_DIR, vf.filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File missing from disk")
    return FileResponse(
        path,
        filename=vf.original_name,
        media_type=vf.mimetype
    )

@router.delete("/{file_id}")
def delete_file(
    file_id: int,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    vf = db.query(VaultFile).filter(VaultFile.id == file_id).first()
    if not vf:
        raise HTTPException(404, "File not found")
    if vf.author_id != current.id and not current.is_admin:
        raise HTTPException(403, "Only the author or admin can delete this file")
    path = os.path.join(UPLOAD_DIR, vf.filename)
    if os.path.exists(path):
        os.remove(path)
    db.delete(vf); db.commit()
    return {"message": "Deleted"}

