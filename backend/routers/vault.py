from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import hashlib, uuid, os
from core.database import get_db
from core.security import get_current_user
from core.validation import clean_text, safe_download_name
from models.vault import VaultFile
from models.user import User

router  = APIRouter(prefix="/api/vault", tags=["vault"])
UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vault_files"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
MAX_UPLOAD_SIZE = 25 * 1024 * 1024

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
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    ext      = os.path.splitext(file.filename)[1][:20]
    stored   = f"{uuid.uuid4().hex}{ext}"
    path     = os.path.join(UPLOAD_DIR, stored)
    hasher = hashlib.sha256()
    size = 0
    with open(path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                f.close()
                os.remove(path)
                raise HTTPException(413, "File too large (max 25MB)")
            hasher.update(chunk)
            f.write(chunk)
    sha256 = hasher.hexdigest()

    vf = VaultFile(
        filename      = stored,
        original_name = safe_download_name(file.filename, fallback=f"file{ext or '.bin'}"),
        mimetype      = file.content_type or "application/octet-stream",
        size          = size,
        sha256        = sha256,
        tags          = clean_text(tags, field="tags", max_len=500),
        description   = clean_text(description, field="description", max_len=4000),
        author        = current.handle,
        author_id     = current.id,
    )
    db.add(vf); db.commit(); db.refresh(vf)
    from core.logger import log_upload; log_upload(current.handle, file.filename, size, file.content_type or "unknown")
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
        filename=safe_download_name(vf.original_name),
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
    from core.logger import log_admin; log_admin(current.handle, "delete_file", vf.original_name)
    return {"message": "Deleted"}
