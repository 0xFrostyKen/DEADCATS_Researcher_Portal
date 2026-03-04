import time
import httpx
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from core.database import get_db
from core.security import get_current_user, require_admin
from core.config import CTFTIME_TEAM_ID
from models.user import User
from models.ctf import CTFEvent, CTFResult, CTFParticipant

router = APIRouter(prefix="/api/ctf", tags=["ctf"])

CTFTIME_HEADERS = {
    "User-Agent": "DEADCATS-Portal/1.0 (private team dashboard)"
}

# ── In-memory TTL cache ───────────────────────────────────────────
_cache: dict = {}   # key → {"data": ..., "expires": float}

def _cached(key: str) -> Optional[dict]:
    entry = _cache.get(key)
    if entry and entry["expires"] > time.time():
        return entry["data"]
    return None

def _set_cache(key: str, data, ttl: int = 300):
    _cache[key] = {"data": data, "expires": time.time() + ttl}


# ── CTFtime proxy endpoints ───────────────────────────────────────

@router.get("/proxy/team")
async def proxy_team(_: User = Depends(get_current_user)):
    """Proxy CTFtime team info (cached 5 min)."""
    cached = _cached("team")
    if cached:
        return cached
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"https://ctftime.org/api/v1/teams/{CTFTIME_TEAM_ID}/",
                headers=CTFTIME_HEADERS
            )
        r.raise_for_status()
        data = r.json()
        _set_cache("team", data, ttl=300)
        return data
    except httpx.HTTPError as e:
        raise HTTPException(502, f"CTFtime API error: {e}")


@router.get("/proxy/upcoming")
async def proxy_upcoming(q: str = "", _: User = Depends(get_current_user)):
    """Proxy upcoming CTFtime events (cached 30 min)."""
    cached = _cached("upcoming")
    if not cached:
        now_ts = int(time.time())
        far_ts = now_ts + 60 * 60 * 24 * 120  # next 120 days
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"https://ctftime.org/api/v1/events/?limit=50&start={now_ts}&finish={far_ts}",
                    headers=CTFTIME_HEADERS
                )
            r.raise_for_status()
            cached = r.json()
            _set_cache("upcoming", cached, ttl=1800)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"CTFtime API error: {e}")

    # Filter by search query client-side (already fetched)
    events = cached if isinstance(cached, list) else []
    if q:
        q_lower = q.lower()
        events = [e for e in events if q_lower in e.get("title", "").lower()]
    return events[:20]


# ── Schemas ───────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title:            str
    url:              Optional[str] = None
    ctftime_event_id: Optional[int] = None
    start_time:       Optional[str] = None
    end_time:         Optional[str] = None
    format:           Optional[str] = None
    weight:           Optional[float] = None

class EventUpdate(BaseModel):
    title:            Optional[str]   = None
    url:              Optional[str]   = None
    start_time:       Optional[str]   = None
    end_time:         Optional[str]   = None
    format:           Optional[str]   = None
    weight:           Optional[float] = None
    status:           Optional[str]   = None

class ResultUpsert(BaseModel):
    place:         int
    ctf_points:    float
    rating_points: float

class ParticipantCreate(BaseModel):
    member_handle: str
    points:        float
    notes:         Optional[str] = None


# ── Helper ────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None

def _event_full(ev: CTFEvent, db: Session) -> dict:
    """Return event dict enriched with result + participants."""
    d = ev.to_dict()
    result = db.query(CTFResult).filter(CTFResult.event_id == ev.id).first()
    d["result"] = result.to_dict() if result else None
    participants = db.query(CTFParticipant).filter(CTFParticipant.event_id == ev.id).all()
    d["participants"] = [p.to_dict() for p in participants]
    return d


# ── Event endpoints ───────────────────────────────────────────────

@router.get("/events")
def list_events(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """All tracked CTF events with nested result + participants."""
    events = db.query(CTFEvent).order_by(CTFEvent.start_time.asc().nullslast()).all()
    return [_event_full(ev, db) for ev in events]


@router.post("/events", status_code=201)
def create_event(
    payload: EventCreate,
    db:      Session = Depends(get_db),
    admin:   User    = Depends(require_admin),
):
    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "Title required.")
    ev = CTFEvent(
        title            = title,
        url              = payload.url,
        ctftime_event_id = payload.ctftime_event_id,
        start_time       = _parse_dt(payload.start_time),
        end_time         = _parse_dt(payload.end_time),
        format           = payload.format,
        weight           = payload.weight,
        status           = "upcoming",
        added_by         = admin.handle,
    )
    db.add(ev); db.commit(); db.refresh(ev)
    return _event_full(ev, db)


@router.patch("/events/{event_id}")
def update_event(
    event_id: int,
    payload:  EventUpdate,
    db:       Session = Depends(get_db),
    admin:    User    = Depends(require_admin),
):
    ev = db.query(CTFEvent).filter(CTFEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Event not found.")
    if payload.title  is not None: ev.title      = payload.title.strip()
    if payload.url    is not None: ev.url         = payload.url
    if payload.format is not None: ev.format      = payload.format
    if payload.weight is not None: ev.weight      = payload.weight
    if payload.status is not None:
        if payload.status not in ("upcoming", "completed"):
            raise HTTPException(400, "status must be 'upcoming' or 'completed'.")
        ev.status = payload.status
    if payload.start_time is not None: ev.start_time = _parse_dt(payload.start_time)
    if payload.end_time   is not None: ev.end_time   = _parse_dt(payload.end_time)
    db.commit(); db.refresh(ev)
    return _event_full(ev, db)


@router.delete("/events/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    db:       Session = Depends(get_db),
    admin:    User    = Depends(require_admin),
):
    ev = db.query(CTFEvent).filter(CTFEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Event not found.")
    # Cascade delete result + participants
    db.query(CTFResult).filter(CTFResult.event_id == event_id).delete()
    db.query(CTFParticipant).filter(CTFParticipant.event_id == event_id).delete()
    db.delete(ev); db.commit()


# ── Result endpoints ──────────────────────────────────────────────

@router.post("/events/{event_id}/result", status_code=201)
def upsert_result(
    event_id: int,
    payload:  ResultUpsert,
    db:       Session = Depends(get_db),
    admin:    User    = Depends(require_admin),
):
    ev = db.query(CTFEvent).filter(CTFEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Event not found.")
    result = db.query(CTFResult).filter(CTFResult.event_id == event_id).first()
    if result:
        result.place         = payload.place
        result.ctf_points    = payload.ctf_points
        result.rating_points = payload.rating_points
        result.added_by      = admin.handle
        result.added_at      = datetime.now(timezone.utc)
    else:
        result = CTFResult(
            event_id      = event_id,
            place         = payload.place,
            ctf_points    = payload.ctf_points,
            rating_points = payload.rating_points,
            added_by      = admin.handle,
        )
        db.add(result)
    # Auto-mark event as completed when result is added
    ev.status = "completed"
    db.commit(); db.refresh(result)
    return result.to_dict()


# ── Participant endpoints ─────────────────────────────────────────

@router.post("/events/{event_id}/participants", status_code=201)
def add_participant(
    event_id: int,
    payload:  ParticipantCreate,
    db:       Session = Depends(get_db),
    admin:    User    = Depends(require_admin),
):
    ev = db.query(CTFEvent).filter(CTFEvent.id == event_id).first()
    if not ev:
        raise HTTPException(404, "Event not found.")
    handle = payload.member_handle.strip()
    if not handle:
        raise HTTPException(400, "member_handle required.")
    p = CTFParticipant(
        event_id      = event_id,
        member_handle = handle,
        points        = payload.points,
        notes         = payload.notes,
        added_by      = admin.handle,
    )
    db.add(p); db.commit(); db.refresh(p)
    return p.to_dict()


@router.delete("/participants/{participant_id}", status_code=204)
def delete_participant(
    participant_id: int,
    db:             Session = Depends(get_db),
    admin:          User    = Depends(require_admin),
):
    p = db.query(CTFParticipant).filter(CTFParticipant.id == participant_id).first()
    if not p:
        raise HTTPException(404, "Participant not found.")
    db.delete(p); db.commit()
