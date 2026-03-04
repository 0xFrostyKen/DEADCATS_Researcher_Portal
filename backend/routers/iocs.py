from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from core.database import get_db
from core.security import get_current_user, require_admin
from models.ioc import IOC
from models.user import User

router = APIRouter(prefix="/api/iocs", tags=["iocs"])

IOC_TYPES     = ["ip", "domain", "hash", "url", "email", "cve"]
IOC_SEVERITIES= ["low", "medium", "high", "critical"]

class CreateIOCRequest(BaseModel):
    type:     str
    value:    str
    tags:     Optional[str] = ""
    severity: Optional[str] = "medium"
    notes:    Optional[str] = ""

class UpdateIOCRequest(BaseModel):
    tags:     Optional[str] = None
    severity: Optional[str] = None
    notes:    Optional[str] = None

@router.get("/")
def list_iocs(
    type:     Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    search:   Optional[str] = Query(None),
    db:       Session = Depends(get_db),
    _:        User    = Depends(get_current_user)
):
    query = db.query(IOC)
    if type:     query = query.filter(IOC.type == type)
    if severity: query = query.filter(IOC.severity == severity)
    if search:   query = query.filter(IOC.value.ilike(f"%{search}%"))
    iocs = query.order_by(IOC.created_at.desc()).all()
    return [i.to_dict() for i in iocs]

@router.post("/", status_code=201)
def create_ioc(
    payload: CreateIOCRequest,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    if payload.type not in IOC_TYPES:
        raise HTTPException(400, f"Invalid type. Choose from: {IOC_TYPES}")
    if payload.severity not in IOC_SEVERITIES:
        raise HTTPException(400, f"Invalid severity.")
    ioc = IOC(
        type      = payload.type,
        value     = payload.value,
        tags      = payload.tags,
        severity  = payload.severity,
        notes     = payload.notes,
        author    = current.handle,
        author_id = current.id,
    )
    db.add(ioc); db.commit(); db.refresh(ioc)
    return ioc.to_dict()

@router.delete("/{ioc_id}")
def delete_ioc(
    ioc_id:  int,
    db:      Session = Depends(get_db),
    current: User    = Depends(get_current_user)
):
    ioc = db.query(IOC).filter(IOC.id == ioc_id).first()
    if not ioc:
        raise HTTPException(404, "IOC not found")
    if ioc.author_id != current.id and not current.is_admin:
        raise HTTPException(403, "Only the author or admin can delete this IOC")
    db.delete(ioc); db.commit()
    return {"message": "Deleted"}

@router.get("/export")
def export_iocs(
    db: Session = Depends(get_db),
    _:  User    = Depends(get_current_user)
):
    from fastapi.responses import StreamingResponse
    import csv, io
    iocs = db.query(IOC).order_by(IOC.created_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id","type","value","severity","tags","notes","author","created_at"])
    for i in iocs:
        writer.writerow([i.id, i.type, i.value, i.severity, i.tags, i.notes, i.author, i.created_at])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=deadcats_iocs.csv"}
    )
