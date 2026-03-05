from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from contextlib import asynccontextmanager
import os as _os
from sqlalchemy import text

from core.config import FRONTEND_ORIGIN, ADMIN_HANDLE, ADMIN_PASSWORD
from core.database import engine, Base
from core.security import hash_password
from models.user import User
from routers import auth, users, notes, achievements, announcements, iocs, vault, bookmarks, whiteboard, ctf
import models.bookmark          # ensure table is created on startup
import models.goal               # ensure table is created on startup
import models.whiteboard_config  # ensure table is created on startup
import models.ctf                # ensure tables are created on startup
from core.database import get_db
from fastapi import Depends
from core.security import get_current_user

# ── Startup ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    # Minimal startup migration for existing deployments.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE ctf_events ADD COLUMN IF NOT EXISTS description TEXT"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_status VARCHAR(40) DEFAULT 'available'"))

    from core.database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.handle == ADMIN_HANDLE).first()
        if not existing:
            admin = User(
                handle   = ADMIN_HANDLE,
                password = hash_password(ADMIN_PASSWORD),
                emoji    = "💀",
                rank     = "Arch Duke",
                is_admin = True,
                bio      = "Platform administrator.",
            )
            db.add(admin)
            db.commit()
            print(f"[DEADCATS] Admin account '{ADMIN_HANDLE}' created.")
        else:
            print(f"[DEADCATS] Admin account '{ADMIN_HANDLE}' already exists.")
    finally:
        db.close()

    yield

# ── App ───────────────────────────────────────────────────────────

app = FastAPI(
    title       = "DEADCATS Research Portal API",
    description = "Backend API for the DEADCATS internal research platform.",
    version     = "1.0.0",
    lifespan    = lifespan,
    docs_url    = "/api/docs",
    redoc_url   = "/api/redoc",
)

# ── Security headers middleware ───────────────────────────────────

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]     = "camera=(), microphone=(), geolocation=()"
    return response

# ── CORS ─────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = [FRONTEND_ORIGIN],
    allow_credentials = True,
    allow_methods     = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers     = ["Authorization", "Content-Type"],
)

# ── Routers ───────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(notes.router)
app.include_router(achievements.router)
app.include_router(announcements.router)
app.include_router(iocs.router)
app.include_router(vault.router)
app.include_router(bookmarks.router)
app.include_router(whiteboard.router)
app.include_router(ctf.router)

# ── Health / Stats ────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(db = Depends(get_db), _: User = Depends(get_current_user)):
    from models.user import User as UserModel
    from models.note import Note
    from sqlalchemy import func
    from models.ioc import IOC
    total_members = db.query(func.count(UserModel.id)).scalar()
    total_notes   = db.query(func.count(Note.id)).scalar()
    total_iocs    = db.query(func.count(IOC.id)).scalar()
    return {
        "total_members": total_members,
        "total_notes":   total_notes,
        "total_iocs":    total_iocs,
    }

@app.get("/api/health")
def health():
    return {"status": "operational", "platform": "DEADCATS v1.0.0"}

# ── Profile uploads (path traversal protected) ────────────────────

_UPLOAD_DIR  = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "profile_uploads"))
_ALLOWED_FOLDERS = {"avatars", "banners"}

@app.get("/profile_uploads/{folder}/{filename}")
async def serve_upload(folder: str, filename: str):
    # Prevent path traversal and restrict to known sub-folders
    if folder not in _ALLOWED_FOLDERS:
        raise HTTPException(404, "Not found")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = _os.path.join(_UPLOAD_DIR, folder, filename)
    # Ensure resolved path stays inside UPLOAD_DIR
    if not _os.path.abspath(path).startswith(_UPLOAD_DIR):
        raise HTTPException(400, "Invalid path")
    if not _os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path)

# ── Frontend static files ─────────────────────────────────────────

class SafeStaticFiles(StaticFiles):
    """Static file wrapper that blocks sensitive project paths."""

    _DENY_PREFIXES = {
        "backend/",
        ".git/",
        "profile_uploads/",
        "vault_files/",
    }
    _DENY_EXACT = {"agents.md"}

    async def get_response(self, path: str, scope):
        normalized = _os.path.normpath(path).replace("\\", "/").lstrip("/")
        if normalized in {".", ""}:
            return await super().get_response(path, scope)
        if normalized == ".." or normalized.startswith("../"):
            raise HTTPException(status_code=404, detail="Not found")
        lowered = normalized.lower()
        if lowered in self._DENY_EXACT:
            raise HTTPException(status_code=404, detail="Not found")
        if any(lowered == prefix[:-1] or lowered.startswith(prefix) for prefix in self._DENY_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        if any(part.startswith(".") for part in lowered.split("/")):
            raise HTTPException(status_code=404, detail="Not found")
        return await super().get_response(path, scope)


app.mount(
    "/",
    SafeStaticFiles(
        directory=_os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..")),
        html=True,
    ),
    name="frontend",
)
