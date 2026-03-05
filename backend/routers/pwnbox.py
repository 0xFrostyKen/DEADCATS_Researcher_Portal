from __future__ import annotations

import asyncio
import fcntl
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import decode_token, get_current_user
from models.user import User

router = APIRouter(prefix="/api/pwnbox", tags=["pwnbox"])

SESSION_TTL_MINUTES = int(os.getenv("PWNBOX_SESSION_TTL_MINUTES", "90"))
PWNBOX_IMAGE = os.getenv("PWNBOX_IMAGE", "pwnbox-base:latest")
PWNBOX_WORKDIR = os.getenv("PWNBOX_WORKDIR", "/home/hacker")
PWNBOX_AUTO_BUILD = os.getenv("PWNBOX_AUTO_BUILD", "true").strip().lower() in {"1", "true", "yes", "on"}
STATE_FILE = Path(os.getenv("PWNBOX_STATE_FILE", str(Path(__file__).resolve().parents[1] / "pwnbox_session_state.json")))
SESSION_LOCK_FILE = Path(os.getenv("PWNBOX_SESSION_LOCK_FILE", str(Path(__file__).resolve().parents[1] / "pwnbox_session.lock")))
IMAGE_LOCK_FILE = Path(os.getenv("PWNBOX_IMAGE_LOCK_FILE", str(Path(__file__).resolve().parents[1] / "pwnbox_image.lock")))


class SessionInfo(BaseModel):
    session_id: str
    owner_user_id: int
    owner_handle: str
    container_id: str
    container_name: str
    status: str
    started_at: datetime
    expires_at: datetime


class SessionState(BaseModel):
    active: bool
    session: SessionInfo | None = None


_active_session: SessionInfo | None = None
_reaper_started = False
_reaper_lock = threading.Lock()

_DEFAULT_PWNBOX_DOCKERFILE = """\
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \\
    bash coreutils ca-certificates python3 python3-pip curl jq \\
    gcc gdb make file less vim-tiny \\
 && rm -rf /var/lib/apt/lists/*
RUN if ! getent passwd 1000 >/dev/null; then useradd -m -u 1000 -s /bin/bash hacker; fi \\
 && mkdir -p /home/hacker \\
 && chown -R 1000:1000 /home/hacker
USER 1000:1000
WORKDIR /home/hacker
CMD ["/bin/sh","-lc","sleep infinity"]
"""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


@contextmanager
def _session_lock():
    with _file_lock(SESSION_LOCK_FILE):
        yield


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


def _docker_client():
    try:
        import docker  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Docker SDK unavailable: {exc}") from exc
    try:
        return docker.from_env()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Docker daemon unavailable: {exc}") from exc


def _ensure_image_exists() -> None:
    # Separate lock so long build doesn't block session status/stop/start locks.
    with _file_lock(IMAGE_LOCK_FILE):
        client = _docker_client()
        try:
            client.images.get(PWNBOX_IMAGE)
            return
        except Exception:
            pass

        if not PWNBOX_AUTO_BUILD:
            raise HTTPException(
                status_code=503,
                detail=f"PwnBox image '{PWNBOX_IMAGE}' not found and auto-build is disabled",
            )

        try:
            with tempfile.TemporaryDirectory(prefix="pwnbox-build-") as td:
                dockerfile = Path(td) / "Dockerfile"
                dockerfile.write_text(_DEFAULT_PWNBOX_DOCKERFILE, encoding="utf-8")
                client.images.build(path=td, dockerfile="Dockerfile", tag=PWNBOX_IMAGE, rm=True, pull=True)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to auto-build PwnBox image: {exc}") from exc


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
    with suppress(Exception):
        c.remove(force=True)


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


def _cleanup_expired_if_needed() -> None:
    global _active_session
    if _active_session and _active_session.expires_at <= _utcnow():
        _stop_remove_container(_active_session.container_id)
        _active_session = None
        _save_state()


def _reconcile_runtime_state() -> None:
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


def _init_state_once() -> None:
    with _session_lock():
        _load_state()
        _reconcile_runtime_state()


def _reaper_loop() -> None:
    while True:
        try:
            with _session_lock():
                _load_state()
                _cleanup_expired_if_needed()
                _reconcile_runtime_state()
        except Exception:
            pass
        time.sleep(20)


def _ensure_reaper_started() -> None:
    global _reaper_started
    with _reaper_lock:
        if _reaper_started:
            return
        t = threading.Thread(target=_reaper_loop, daemon=True, name="pwnbox-reaper")
        t.start()
        _reaper_started = True


@router.get("/health")
def health(_: User = Depends(get_current_user)) -> dict[str, str]:
    _ensure_reaper_started()
    _init_state_once()
    return {"status": "ok", "service": "pwnbox"}


@router.get("/status", response_model=SessionState)
def status(_: User = Depends(get_current_user)) -> SessionState:
    _ensure_reaper_started()
    with _session_lock():
        _load_state()
        _cleanup_expired_if_needed()
        _reconcile_runtime_state()
        return SessionState(active=_active_session is not None, session=_active_session)


@router.post("/start", response_model=SessionInfo, status_code=201)
def start(current: User = Depends(get_current_user)) -> SessionInfo:
    global _active_session
    _ensure_reaper_started()

    # Expensive path (auto build) intentionally outside session lock.
    _ensure_image_exists()

    with _session_lock():
        _load_state()
        _cleanup_expired_if_needed()
        _reconcile_runtime_state()
        if _active_session is not None:
            raise HTTPException(status_code=409, detail="PwnBox session already active")

        now = _utcnow()
        session_id = str(uuid4())
        container = _create_pwnbox_container(session_id)

        _active_session = SessionInfo(
            session_id=session_id,
            owner_user_id=current.id,
            owner_handle=current.handle,
            container_id=container.id,
            container_name=container.name,
            status="active",
            started_at=now,
            expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
        )
        _save_state()
        return _active_session


@router.delete("/stop")
def stop(current: User = Depends(get_current_user)) -> dict[str, str]:
    global _active_session
    _ensure_reaper_started()
    with _session_lock():
        _load_state()
        if _active_session is not None:
            if not current.is_admin and current.handle != _active_session.owner_handle:
                raise HTTPException(status_code=403, detail="Only the active owner (or admin) can stop this session")
            _stop_remove_container(_active_session.container_id)
            _active_session = None
            _save_state()
    return {"message": "PwnBox session stopped"}


def _ws_auth_user(websocket: WebSocket, db: Session) -> User:
    token = websocket.cookies.get("dc_access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    handle = payload.get("sub")
    if not handle:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.query(User).filter(User.handle == handle).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


@router.websocket("/ws/{session_id}")
async def ws_terminal(websocket: WebSocket, session_id: str, db: Session = Depends(get_db)) -> None:
    await websocket.accept()

    try:
        current = _ws_auth_user(websocket, db)
    except HTTPException as exc:
        await websocket.send_text(f"[pwnbox] auth failed: {exc.detail}")
        await websocket.close(code=4401)
        return

    _ensure_reaper_started()
    with _session_lock():
        _load_state()
        _cleanup_expired_if_needed()
        _reconcile_runtime_state()
        if _active_session is None or _active_session.session_id != session_id:
            await websocket.send_text("[pwnbox] session not found or expired")
            await websocket.close(code=4404)
            return
        if not current.is_admin and current.handle != _active_session.owner_handle:
            await websocket.send_text("[pwnbox] only the active owner can attach")
            await websocket.close(code=4403)
            return
        container_id = _active_session.container_id

    try:
        client = _docker_client()
        api = client.api
        exec_id = api.exec_create(
            container=container_id,
            cmd=[
                "/bin/sh",
                "-lc",
                f"cd {PWNBOX_WORKDIR} 2>/dev/null || true; export TERM=xterm-256color; exec /bin/sh -i",
            ],
            stdin=True,
            stdout=True,
            stderr=True,
            tty=True,
            user="1000:1000",
            workdir=PWNBOX_WORKDIR,
        )["Id"]
        sock_obj = api.exec_start(exec_id, tty=True, socket=True)
        raw_sock = getattr(sock_obj, "_sock", sock_obj)
        try:
            raw_sock.settimeout(0.25)
        except Exception:
            pass
    except Exception as exc:
        await websocket.send_text(f"[pwnbox] failed to open shell: {exc}")
        await websocket.close(code=1011)
        return

    await websocket.send_text("[pwnbox] shell connected.\n")

    stop_evt = asyncio.Event()

    async def proc_to_ws() -> None:
        while not stop_evt.is_set():
            try:
                data = await asyncio.to_thread(raw_sock.recv, 4096)
            except TimeoutError:
                continue
            except Exception:
                break
            if not data:
                break
            await websocket.send_text(data.decode("utf-8", errors="replace"))
        stop_evt.set()

    async def ws_to_proc() -> None:
        while not stop_evt.is_set():
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                break

            # Resize control messages from frontend.
            if data.startswith("{"):
                try:
                    msg = json.loads(data)
                except Exception:
                    msg = None
                if isinstance(msg, dict) and msg.get("type") == "resize":
                    cols = int(msg.get("cols") or 0)
                    rows = int(msg.get("rows") or 0)
                    if cols > 0 and rows > 0:
                        with suppress(Exception):
                            await asyncio.to_thread(api.exec_resize, exec_id, height=rows, width=cols)
                    continue

            with suppress(Exception):
                await asyncio.to_thread(raw_sock.sendall, data.encode("utf-8", errors="ignore"))
        stop_evt.set()

    out_task = asyncio.create_task(proc_to_ws())
    in_task = asyncio.create_task(ws_to_proc())

    done, pending = await asyncio.wait({out_task, in_task}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
        with suppress(asyncio.CancelledError):
            await t

    with suppress(Exception):
        raw_sock.close()
    if hasattr(sock_obj, "close"):
        with suppress(Exception):
            sock_obj.close()

    with suppress(WebSocketDisconnect, RuntimeError):
        await websocket.close()
