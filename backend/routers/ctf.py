import time
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from core.database import get_db
from core.security import get_current_user, require_admin
from core.config import CTFTIME_TEAM_ID
from core.validation import clean_text, reject_html
from models.user import User
from models.ctf import CTFEvent, CTFResult, CTFParticipant
from models.announcement import Announcement

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


@router.get("/proxy/results/{year}")
async def proxy_results(year: int, _: User = Depends(get_current_user)):
    """Proxy team results for a given year from CTFtime (cached 30 min)."""
    now_year = datetime.now(timezone.utc).year
    if year < 2010 or year > now_year + 1:
        raise HTTPException(400, "Invalid year")
    key = f"results:{year}"
    cached = _cached(key)
    if cached is not None:
        return cached

    def _iter_events(payload: Any):
        if isinstance(payload, list):
            for ev in payload:
                if isinstance(ev, dict):
                    yield ev
            return
        if isinstance(payload, dict):
            for k, ev in payload.items():
                if isinstance(ev, dict):
                    if "id" not in ev:
                        try:
                            ev = {**ev, "id": int(k)}
                        except Exception:
                            pass
                    yield ev

    def _extract_team_rows(ev: dict, team_id: int):
        candidates = []
        for key in ("scores", "results", "standings", "teams", "scoreboard"):
            v = ev.get(key)
            if isinstance(v, list):
                candidates.extend(v)
        # Some payloads put a flat team row at event level.
        if any(k in ev for k in ("team_id", "team", "place", "points", "score")):
            candidates.append(ev)

        for row in candidates:
            if not isinstance(row, dict):
                continue
            rid = row.get("team_id")
            if rid is None and isinstance(row.get("team"), dict):
                rid = row["team"].get("id")
            if rid is None:
                rid = row.get("id")
            try:
                if int(rid) != team_id:
                    continue
            except Exception:
                continue
            place = row.get("place", row.get("pos", row.get("rank")))
            ctf_points = row.get("ctf_points", row.get("points", row.get("score")))
            rating_points = row.get("rating_points", row.get("rating", row.get("rating_score")))
            yield {
                "task_id": ev.get("id", ev.get("event_id", ev.get("task_id"))),
                "task_name": ev.get("title", ev.get("event", ev.get("name", "Unknown Event"))),
                "place": place,
                "ctf_points": ctf_points,
                "rating_points": rating_points,
            }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://ctftime.org/api/v1/results/{year}/",
                headers=CTFTIME_HEADERS
            )
        r.raise_for_status()
        data = r.json()
        team_id = int(CTFTIME_TEAM_ID)
        tasks: list[dict] = []
        seen: set[int] = set()
        for ev in _iter_events(data):
            for task in _extract_team_rows(ev, team_id):
                tid = task.get("task_id")
                try:
                    tid_int = int(tid)
                except Exception:
                    continue
                if tid_int in seen:
                    continue
                seen.add(tid_int)
                task["task_id"] = tid_int
                tasks.append(task)
        _set_cache(key, tasks, ttl=1800)
        return tasks
    except httpx.HTTPError as e:
        raise HTTPException(502, f"CTFtime API error: {type(e).__name__}: {e}")


# ── Schemas ───────────────────────────────────────────────────────

class EventCreate(BaseModel):
    title:            str = Field(min_length=1, max_length=200)
    url:              Optional[str] = Field(default=None, max_length=500)
    ctftime_event_id: Optional[int] = None
    start_time:       Optional[str] = Field(default=None, max_length=40)
    end_time:         Optional[str] = Field(default=None, max_length=40)
    format:           Optional[str] = Field(default=None, max_length=100)
    weight:           Optional[float] = None
    description:      Optional[str] = Field(default=None, max_length=4000)

class EventUpdate(BaseModel):
    title:            Optional[str]   = Field(default=None, min_length=1, max_length=200)
    url:              Optional[str]   = Field(default=None, max_length=500)
    start_time:       Optional[str]   = Field(default=None, max_length=40)
    end_time:         Optional[str]   = Field(default=None, max_length=40)
    format:           Optional[str]   = Field(default=None, max_length=100)
    weight:           Optional[float] = None
    description:      Optional[str]   = Field(default=None, max_length=4000)
    status:           Optional[str]   = Field(default=None, max_length=20)

class ResultUpsert(BaseModel):
    place:         int
    ctf_points:    float
    rating_points: float

class ParticipantCreate(BaseModel):
    member_handle: str = Field(min_length=1, max_length=50)
    points:        float
    notes:         Optional[str] = Field(default=None, max_length=1000)


# ── Helper ────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Invalid datetime format. Use ISO-8601.")

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
    title = reject_html(clean_text(payload.title, field="title", max_len=200), field="title")
    if not title:
        raise HTTPException(400, "Title required.")
    start_dt = _parse_dt(payload.start_time)
    end_dt = _parse_dt(payload.end_time)
    if start_dt and end_dt and end_dt < start_dt:
        raise HTTPException(400, "end_time cannot be earlier than start_time.")
    ev = CTFEvent(
        title            = title,
        url              = clean_text(payload.url, field="url", max_len=500),
        ctftime_event_id = payload.ctftime_event_id,
        start_time       = start_dt,
        end_time         = end_dt,
        format           = clean_text(payload.format, field="format", max_len=100),
        weight           = payload.weight,
        description      = clean_text(payload.description, field="description", max_len=4000),
        status           = "upcoming",
        added_by         = admin.handle,
    )
    db.add(ev); db.commit(); db.refresh(ev)
    now = datetime.now(timezone.utc)
    expires_at = start_dt if (start_dt and start_dt > now) else (now + timedelta(days=14))
    schedule_line = start_dt.strftime("%Y-%m-%d %H:%M UTC") if start_dt else "TBA"
    summary = f"{title} | {schedule_line}"
    if ev.url:
        summary += f"\n{ev.url}"
    a = Announcement(
        title=f"Upcoming CTF: {title}",
        content=summary,
        type="notice",
        author=admin.handle,
        expires_at=expires_at,
        pinned=False,
    )
    db.add(a); db.commit()
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
    if payload.title  is not None: ev.title      = reject_html(clean_text(payload.title, field="title", max_len=200), field="title")
    if payload.url    is not None: ev.url         = clean_text(payload.url, field="url", max_len=500)
    if payload.format is not None: ev.format      = clean_text(payload.format, field="format", max_len=100)
    if payload.weight is not None: ev.weight      = payload.weight
    if payload.description is not None: ev.description = clean_text(payload.description, field="description", max_len=4000)
    if payload.status is not None:
        if payload.status not in ("upcoming", "completed"):
            raise HTTPException(400, "status must be 'upcoming' or 'completed'.")
        ev.status = payload.status
    if payload.start_time is not None:
        ev.start_time = _parse_dt(payload.start_time)
    if payload.end_time is not None:
        ev.end_time = _parse_dt(payload.end_time)
    if ev.start_time and ev.end_time and ev.end_time < ev.start_time:
        raise HTTPException(400, "end_time cannot be earlier than start_time.")
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
    handle = reject_html(clean_text(payload.member_handle, field="member_handle", max_len=50), field="member_handle")
    if not handle:
        raise HTTPException(400, "member_handle required.")
    p = CTFParticipant(
        event_id      = event_id,
        member_handle = handle,
        points        = payload.points,
        notes         = clean_text(payload.notes, field="notes", max_len=1000),
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
