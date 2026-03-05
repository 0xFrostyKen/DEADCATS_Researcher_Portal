from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="PwnBox API", version="0.2.0")

SESSION_TTL_MINUTES = int(os.getenv("PWNBOX_SESSION_TTL_MINUTES", "90"))
PWNBOX_IMAGE = os.getenv("PWNBOX_IMAGE", "pwnbox-base:latest")
PWNBOX_WORKDIR = os.getenv("PWNBOX_WORKDIR", "/home/hacker")
STATE_FILE = Path(os.getenv("PWNBOX_STATE_FILE", str(Path(__file__).with_name("session_state.json"))))
PWNBOX_ALLOWED_ORIGINS = os.getenv(
    "PWNBOX_ALLOWED_ORIGINS",
    "http://127.0.0.1:8001,http://localhost:8001,http://127.0.0.1:8000,http://localhost:8000",
)
ALLOWED_ORIGINS = [o.strip() for o in PWNBOX_ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SessionInfo(BaseModel):
    session_id: str
    owner_user_id: int
    owner_handle: str
    container_id: str
    container_name: str
    status: str
    started_at: datetime
    expires_at: datetime


class StartRequest(BaseModel):
    owner_user_id: int
    owner_handle: str


class SessionState(BaseModel):
    active: bool
    session: SessionInfo | None = None


_state_lock = Lock()
_active_session: SessionInfo | None = None


# -----------------------------
# Time / state helpers
# -----------------------------
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_session(session: SessionInfo | None) -> dict | None:
    if session is None:
        return None
    data = session.model_dump()
    data["started_at"] = session.started_at.isoformat()
    data["expires_at"] = session.expires_at.isoformat()
    return data


def _deserialize_session(data: dict | None) -> SessionInfo | None:
    if not data:
        return None
    payload = dict(data)
    payload["started_at"] = datetime.fromisoformat(payload["started_at"])
    payload["expires_at"] = datetime.fromisoformat(payload["expires_at"])
    return SessionInfo(**payload)


def _save_state() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"session": _serialize_session(_active_session)}, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _load_state() -> None:
    global _active_session
    if not STATE_FILE.exists():
        _active_session = None
        return
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        _active_session = _deserialize_session(raw.get("session"))
    except Exception:
        _active_session = None


# -----------------------------
# Docker helpers
# -----------------------------
def _docker_client():
    try:
        import docker  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Docker SDK unavailable: {exc}") from exc
    try:
        return docker.from_env()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}") from exc


def _container_alive(container_id: str) -> bool:
    client = _docker_client()
    try:
        c = client.containers.get(container_id)
        c.reload()
        return c.status in {"running", "created", "restarting"}
    except Exception:
        return False


def _stop_remove_container(container_id: str) -> None:
    client = _docker_client()
    try:
        c = client.containers.get(container_id)
    except Exception:
        return
    try:
        if c.status == "running":
            c.stop(timeout=5)
    except Exception:
        pass
    try:
        c.remove(force=True)
    except Exception:
        pass


def _create_pwnbox_container(session_id: str):
    client = _docker_client()
    name = f"pwnbox-{session_id[:8]}"
    try:
        c = client.containers.run(
            image=PWNBOX_IMAGE,
            command=["/bin/sh", "-lc", "sleep infinity"],
            name=name,
            detach=True,
            tty=True,
            stdin_open=True,
            user="1000:1000",
            working_dir=PWNBOX_WORKDIR,
            mem_limit="1024m",
            nano_cpus=int(1e9),
            pids_limit=256,
            network_mode="none",
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
            read_only=False,
            tmpfs={"/tmp": "rw,noexec,nosuid,size=128m"},
            labels={
                "deadcats.service": "pwnbox",
                "deadcats.session_id": session_id,
            },
        )
        c.reload()
        return c
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start PwnBox container: {exc}") from exc


# -----------------------------
# Session reconciliation
# -----------------------------
def _cleanup_expired_if_needed() -> None:
    global _active_session
    if _active_session and _active_session.expires_at <= _utcnow():
        _stop_remove_container(_active_session.container_id)
        _active_session = None
        _save_state()


def _reconcile_runtime_state() -> None:
    """Reconcile saved state against container runtime on startup/status calls."""
    global _active_session
    if _active_session is None:
        return
    if _active_session.expires_at <= _utcnow():
        _stop_remove_container(_active_session.container_id)
        _active_session = None
        _save_state()
        return
    if not _container_alive(_active_session.container_id):
        _active_session = None
        _save_state()


@app.on_event("startup")
def on_startup() -> None:
    with _state_lock:
        _load_state()
        _reconcile_runtime_state()


# -----------------------------
# API routes
# -----------------------------
@app.get("/api/pwnbox/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pwnbox-api"}


@app.get("/api/pwnbox/status", response_model=SessionState)
def status() -> SessionState:
    with _state_lock:
        _cleanup_expired_if_needed()
        _reconcile_runtime_state()
        return SessionState(active=_active_session is not None, session=_active_session)


@app.post("/api/pwnbox/start", response_model=SessionInfo, status_code=201)
def start(payload: StartRequest) -> SessionInfo:
    global _active_session
    with _state_lock:
        _cleanup_expired_if_needed()
        _reconcile_runtime_state()
        if _active_session is not None:
            raise HTTPException(status_code=409, detail="PwnBox session already active")

        now = _utcnow()
        session_id = str(uuid4())
        container = _create_pwnbox_container(session_id)

        _active_session = SessionInfo(
            session_id=session_id,
            owner_user_id=payload.owner_user_id,
            owner_handle=payload.owner_handle,
            container_id=container.id,
            container_name=container.name,
            status="active",
            started_at=now,
            expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
        )
        _save_state()
        return _active_session


@app.delete("/api/pwnbox/stop")
def stop() -> dict[str, str]:
    global _active_session
    with _state_lock:
        if _active_session is not None:
            _stop_remove_container(_active_session.container_id)
            _active_session = None
            _save_state()
    return {"message": "PwnBox session stopped"}


@app.websocket("/api/pwnbox/ws/{session_id}")
async def ws_terminal(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    with _state_lock:
        _cleanup_expired_if_needed()
        _reconcile_runtime_state()
        if _active_session is None or _active_session.session_id != session_id:
            await websocket.send_text("[pwnbox] session not found or expired")
            await websocket.close(code=4404)
            return
        container_id = _active_session.container_id

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "exec",
            "-i",
            container_id,
            "/bin/sh",
            "-lc",
            (
                f"cd {PWNBOX_WORKDIR} 2>/dev/null || true; "
                "export TERM=xterm-256color; "
                "exec python3 -c \"import os,pty; os.environ.setdefault('TERM','xterm-256color'); pty.spawn(['/bin/sh','-i'])\""
            ),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except Exception as exc:
        await websocket.send_text(f"[pwnbox] failed to open shell: {exc}")
        await websocket.close(code=1011)
        return

    await websocket.send_text("[pwnbox] shell connected.")

    async def proc_to_ws() -> None:
        while True:
            if not proc.stdout:
                return
            chunk = await proc.stdout.read(1024)
            if not chunk:
                return
            await websocket.send_text(chunk.decode("utf-8", errors="replace"))

    async def ws_to_proc() -> None:
        while True:
            data = await websocket.receive_text()
            # Optional no-op support for JSON resize messages from client.
            if data.startswith("{") and "\"type\":\"resize\"" in data.replace(" ", ""):
                continue
            if not proc.stdin:
                return
            proc.stdin.write(data.encode("utf-8", errors="ignore"))
            await proc.stdin.drain()

    out_task = asyncio.create_task(proc_to_ws())
    in_task = asyncio.create_task(ws_to_proc())

    done, pending = await asyncio.wait({out_task, in_task}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
        with suppress(asyncio.CancelledError):
            await t

    if proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.terminate()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=1.5)
    if proc.returncode is None:
        with suppress(ProcessLookupError):
            proc.kill()

    with suppress(WebSocketDisconnect, RuntimeError):
        await websocket.close()
