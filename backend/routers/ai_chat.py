from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import httpx

from core.database import get_db
from core.security import get_current_user
from core.validation import clean_text
from core.config import (
    AI_CHAT_BASE_URL,
    AI_CHAT_API_KEY,
    AI_CHAT_MODEL,
    AI_CHAT_TIMEOUT_SECONDS,
    AI_CHAT_SITE_URL,
    AI_CHAT_SITE_NAME,
    AI_CHAT_PROVIDER,
    AI_CHAT_GEMINI_API_KEY,
)
from models.user import User
from models.chat_message import ChatMessage
from models.note import Note
from models.ioc import IOC
from models.vault import VaultFile
from models.ctf import CTFEvent

router = APIRouter(prefix="/api/ai-chat", tags=["ai-chat"])


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _fallback_reply(db: Session, current: User) -> str:
    total_notes = db.query(Note).count()
    total_iocs = db.query(IOC).count()
    total_files = db.query(VaultFile).count()
    return (
        "AI provider is not configured yet. "
        "Set AI_CHAT_API_KEY (or AI_CHAT_GEMINI_API_KEY for Gemini) in .env to enable real LLM chat. "
        f"Portal snapshot: notes={total_notes}, iocs={total_iocs}, files={total_files}, user={current.handle}."
    )


def _context_block(db: Session, current: User) -> str:
    total_notes = db.query(Note).count()
    total_iocs = db.query(IOC).count()
    total_files = db.query(VaultFile).count()

    recent_iocs = db.query(IOC).order_by(IOC.created_at.desc()).limit(5).all()
    recent_notes = (
        db.query(Note)
        .order_by(Note.updated_at.desc().nullslast(), Note.created_at.desc())
        .limit(5)
        .all()
    )
    upcoming = (
        db.query(CTFEvent)
        .filter(CTFEvent.status == "upcoming")
        .order_by(CTFEvent.start_time.asc().nullslast(), CTFEvent.created_at.desc())
        .limit(4)
        .all()
    )

    ioc_lines = [f"- {i.type}:{i.value} [{i.severity}] by {i.author}" for i in recent_iocs]
    note_lines = [f"- {n.title} by {n.author_handle}" for n in recent_notes]
    ctf_lines = [
        f"- {ev.title} ({ev.start_time.isoformat() if ev.start_time else 'date TBD'})"
        for ev in upcoming
    ]

    return (
        f"User: {current.handle} (admin={current.is_admin})\n"
        f"Portal totals: notes={total_notes}, iocs={total_iocs}, files={total_files}\n\n"
        f"Recent IOCs:\n{chr(10).join(ioc_lines) if ioc_lines else '- none'}\n\n"
        f"Recent Notes:\n{chr(10).join(note_lines) if note_lines else '- none'}\n\n"
        f"Upcoming CTF:\n{chr(10).join(ctf_lines) if ctf_lines else '- none'}"
    )


def _build_messages(db: Session, current: User, prompt: str):
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(16)
        .all()
    )
    history.reverse()

    system_text = (
        "You are DEADCATS AI assistant for a cybersecurity research portal. "
        "Answer directly and concisely. Prefer actionable cyber research guidance. "
        "Do not fabricate portal facts; use provided context. "
        "If data is missing, say so clearly."
    )

    messages = [{"role": "system", "content": system_text}]
    messages.append({"role": "system", "content": "Portal context:\n" + _context_block(db, current)})

    for row in history:
        if row.role in {"user", "assistant"}:
            messages.append({"role": row.role, "content": row.content})

    messages.append({"role": "user", "content": prompt})
    return messages


def _call_openai_compatible(messages):
    if not AI_CHAT_API_KEY:
        return None

    url = f"{AI_CHAT_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {AI_CHAT_API_KEY}", "Content-Type": "application/json"}
    if AI_CHAT_SITE_URL:
        headers["HTTP-Referer"] = AI_CHAT_SITE_URL
    if AI_CHAT_SITE_NAME:
        headers["X-Title"] = AI_CHAT_SITE_NAME

    payload = {
        "model": AI_CHAT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 700,
    }

    with httpx.Client(timeout=AI_CHAT_TIMEOUT_SECONDS) as client:
        res = client.post(url, headers=headers, json=payload)
        if res.status_code >= 400:
            detail = ""
            try:
                detail = res.json().get("error", {}).get("message", "")
            except Exception:
                detail = res.text[:180]
            raise HTTPException(status_code=502, detail=f"AI provider error: {detail or 'request failed'}")

        data = res.json()
        choices = data.get("choices") or []
        if not choices:
            raise HTTPException(status_code=502, detail="AI provider returned no choices")
        msg = choices[0].get("message", {})
        content = (msg.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=502, detail="AI provider returned empty content")
        return content


def _call_gemini(messages):
    gemini_key = AI_CHAT_GEMINI_API_KEY or AI_CHAT_API_KEY
    if not gemini_key:
        return None

    base = AI_CHAT_BASE_URL or "https://generativelanguage.googleapis.com/v1beta"
    if "/v1" not in base:
        base = "https://generativelanguage.googleapis.com/v1beta"
    url = f"{base}/models/{AI_CHAT_MODEL}:generateContent?key={gemini_key}"

    system_parts = []
    convo_lines = []
    for m in messages:
        role = m.get("role", "user")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
        elif role == "assistant":
            convo_lines.append(f"Assistant: {content}")
        else:
            convo_lines.append(f"User: {content}")

    system_text = "\n\n".join(system_parts).strip()
    convo_text = "\n".join(convo_lines).strip()

    payload = {
        "contents": [{"role": "user", "parts": [{"text": convo_text}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 700},
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    with httpx.Client(timeout=AI_CHAT_TIMEOUT_SECONDS) as client:
        res = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if res.status_code >= 400:
            detail = ""
            try:
                detail = res.json().get("error", {}).get("message", "")
            except Exception:
                detail = res.text[:180]
            raise HTTPException(status_code=502, detail=f"Gemini provider error: {detail or 'request failed'}")

        data = res.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise HTTPException(status_code=502, detail="Gemini returned no candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "\n".join((p.get("text") or "").strip() for p in parts if p.get("text")).strip()
        if not text:
            raise HTTPException(status_code=502, detail="Gemini returned empty content")
        return text


def _call_llm(messages):
    provider = (AI_CHAT_PROVIDER or "openai").lower()
    if provider == "gemini":
        return _call_gemini(messages)
    return _call_openai_compatible(messages)


@router.get("/history")
def get_history(
    limit: int = Query(default=80, ge=1, le=300),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == current.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    return [r.to_dict() for r in rows]


@router.delete("/history")
def clear_history(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    db.query(ChatMessage).filter(ChatMessage.user_id == current.id).delete()
    db.commit()
    return {"message": "Conversation cleared"}


@router.post("/message")
def send_message(
    payload: SendMessageRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    user_message = clean_text(payload.message, field="message", max_len=4000, strip=False).strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_row = ChatMessage(user_id=current.id, role="user", content=user_message)
    db.add(user_row)
    db.flush()

    llm_messages = _build_messages(db, current, user_message)
    assistant_text = _call_llm(llm_messages) or _fallback_reply(db, current)

    assistant_row = ChatMessage(user_id=current.id, role="assistant", content=assistant_text)
    db.add(assistant_row)
    db.commit()
    db.refresh(user_row)
    db.refresh(assistant_row)

    return {
        "user_message": user_row.to_dict(),
        "assistant_message": assistant_row.to_dict(),
        "provider": {
            "enabled": bool((AI_CHAT_GEMINI_API_KEY or AI_CHAT_API_KEY) if AI_CHAT_PROVIDER == "gemini" else AI_CHAT_API_KEY),
            "type": AI_CHAT_PROVIDER,
            "base_url": AI_CHAT_BASE_URL,
            "model": AI_CHAT_MODEL,
        },
    }
