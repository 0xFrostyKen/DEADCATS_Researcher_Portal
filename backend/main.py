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
from routers import auth, users, notes, achievements, announcements, iocs, vault, bookmarks, whiteboard, ctf, pwnbox, ai_chat
import models.bookmark
import models.goal
import models.whiteboard_config
import models.ctf
import models.chat_message
from core.database import get_db
from fastapi import Depends
from core.security import get_current_user

# ── Startup ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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

    from core.logger import purge_old_logs
    purge_old_logs()
    print("[DEADCATS] Old logs purged.")

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
app.include_router(pwnbox.router)
app.include_router(ai_chat.router)

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

# ── Monitor endpoint ──────────────────────────────────────────────

@app.get("/api/monitor")
def monitor(db = Depends(get_db), current: User = Depends(get_current_user)):
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    import psutil, platform
    from core.logger import read_log
    from models.user import User as UserModel
    from sqlalchemy import func

    cpu    = psutil.cpu_percent(interval=0.5)
    ram    = psutil.virtual_memory()
    disk   = psutil.disk_usage('/')
    uptime = int(psutil.boot_time())

    total_users = db.query(func.count(UserModel.id)).scalar()

    auth_logs   = read_log("auth.log",    100)
    admin_logs  = read_log("admin.log",   50)
    upload_logs = read_log("uploads.log", 50)
    ioc_logs    = read_log("iocs.log",    50)
    alerts      = read_log("alerts.log",  50)

    success_logins = sum(1 for e in auth_logs if e.get("success"))
    failed_logins  = sum(1 for e in auth_logs if not e.get("success"))

    return {
        "system": {
            "cpu_percent": cpu,
            "ram_total":   ram.total,
            "ram_used":    ram.used,
            "ram_percent": ram.percent,
            "disk_total":  disk.total,
            "disk_used":   disk.used,
            "disk_percent":disk.percent,
            "boot_time":   uptime,
            "platform":    platform.system(),
        },
        "stats": {
            "total_users":    total_users,
            "success_logins": success_logins,
            "failed_logins":  failed_logins,
            "total_uploads":  len(upload_logs),
            "total_iocs":     len(ioc_logs),
        },
        "logs": {
            "auth":    auth_logs[:20],
            "admin":   admin_logs[:20],
            "uploads": upload_logs[:20],
            "iocs":    ioc_logs[:20],
            "alerts":  alerts[:20],
        }
    }

# ── Profile uploads (path traversal protected) ────────────────────

_PROFILE_UPLOAD_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", "profile_uploads"))
_ALLOWED_FOLDERS    = {"avatars", "banners"}

def _serve_profile_upload(folder: str, filename: str):
    if folder not in _ALLOWED_FOLDERS:
        raise HTTPException(404, "Not found")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    path = _os.path.join(_PROFILE_UPLOAD_DIR, folder, filename)
    if not _os.path.abspath(path).startswith(_PROFILE_UPLOAD_DIR):
        raise HTTPException(400, "Invalid path")
    if not _os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path)

@app.get("/profile_uploads/{folder}/{filename}")
async def serve_profile_upload(folder: str, filename: str):
    return _serve_profile_upload(folder, filename)

@app.get("/uploads/{folder}/{filename}")
async def serve_upload_legacy(folder: str, filename: str):
    # Backward-compatible alias for older URLs.
    return _serve_profile_upload(folder, filename)

# ── Frontend static files ─────────────────────────────────────────

class SafeStaticFiles(StaticFiles):
    _DENY_PREFIXES = {
        "backend/",
        ".git/",
        "profile_uploads/",
        "vault_files/",
        "logs/",
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


# ── THIS MUST BE LAST ─────────────────────────────────────────────
app.mount(
    "/",
    SafeStaticFiles(
        directory=_os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..")),
        html=True,
    ),
    name="frontend",
)
