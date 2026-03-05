from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
import re
from core.database import get_db
from core.security import verify_password, hash_password, create_token, get_current_user
from core.config import (
    REGISTER_TOKEN,
    MASTER_HANDLE,
    ALLOW_SELF_REGISTER,
    COOKIE_SECURE,
    COOKIE_SAMESITE,
    JWT_EXPIRE_MINUTES,
)
from core.validation import clean_text, reject_html
from models.user import User
from datetime import datetime, timezone

HANDLE_RE = re.compile(r'^[a-zA-Z0-9_]{2,50}$')

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Schemas ───────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    handle:   str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=128)

class TokenResponse(BaseModel):
    access_token: str | None = None
    token_type:   str = "bearer"
    user:         dict

# ── Routes ────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    handle:       str = Field(min_length=2, max_length=50)
    password:     str = Field(min_length=8, max_length=128)
    access_token: str = Field(min_length=1, max_length=256)


def _set_auth_cookie(response: Response, token: str):
    response.set_cookie(
        key="dc_access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        max_age=JWT_EXPIRE_MINUTES * 60,
        path="/",
    )


def _clear_auth_cookie(response: Response):
    response.delete_cookie(key="dc_access_token", path="/")

@router.post("/register", status_code=201)
def register(payload: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    if not ALLOW_SELF_REGISTER:
        raise HTTPException(status_code=403, detail="Self-registration is disabled.")
    handle = reject_html(clean_text(payload.handle, field="Handle", max_len=50), field="Handle")
    password = clean_text(payload.password, field="Password", max_len=128, strip=False)
    access_token = clean_text(payload.access_token, field="Access token", max_len=256, strip=False)

    if len(REGISTER_TOKEN) < 16:
        raise HTTPException(status_code=503, detail="Registration token is not configured securely.")
    if not REGISTER_TOKEN or access_token != REGISTER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid access token.")
    if not HANDLE_RE.match(handle):
        raise HTTPException(status_code=400, detail="Handle must be 2–50 characters, letters/numbers/underscores only.")
    if handle == MASTER_HANDLE:
        raise HTTPException(status_code=400, detail="Handle not available.")
    if db.query(User).filter(User.handle == handle).first():
        raise HTTPException(status_code=409, detail="Handle already taken.")
    user = User(
        handle   = handle,
        password = hash_password(password),
        rank     = "DEADCAT",
        is_admin = False,
    )
    db.add(user); db.commit(); db.refresh(user)
    token = create_token({"sub": user.handle, "is_admin": False})
    _set_auth_cookie(response, token)
    return {"access_token": token, "token_type": "bearer", "user": user.to_dict()}

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    handle = clean_text(payload.handle, field="Handle", max_len=50)
    password = clean_text(payload.password, field="Password", max_len=128, strip=False)
    user = db.query(User).filter(User.handle == handle).first()

    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid handle or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact admin.",
        )

    # Update last seen
    user.last_seen = datetime.now(timezone.utc)
    db.commit()

    token = create_token({"sub": user.handle, "is_admin": user.is_admin})
    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        user=user.to_dict()
    )

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    """Returns the currently authenticated user's profile."""
    return current_user.to_dict()

@router.post("/logout")
def logout(response: Response):
    """
    JWT is stateless — logout is handled client-side by deleting the token.
    This endpoint exists so the frontend has a clean logout call to make.
    """
    _clear_auth_cookie(response)
    return {"message": "Logged out successfully"}
