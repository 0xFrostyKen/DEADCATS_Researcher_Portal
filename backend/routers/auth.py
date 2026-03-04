from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
import re
from core.database import get_db
from core.security import verify_password, hash_password, create_token, get_current_user
from core.config import REGISTER_TOKEN, MASTER_HANDLE
from models.user import User
from datetime import datetime, timezone

HANDLE_RE = re.compile(r'^[a-zA-Z0-9_]{2,50}$')

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Schemas ───────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    handle:   str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         dict

# ── Routes ────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    handle:       str
    password:     str
    access_token: str

@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if not REGISTER_TOKEN or payload.access_token != REGISTER_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid access token.")
    if not HANDLE_RE.match(payload.handle):
        raise HTTPException(status_code=400, detail="Handle must be 2–50 characters, letters/numbers/underscores only.")
    if payload.handle == MASTER_HANDLE:
        raise HTTPException(status_code=400, detail="Handle not available.")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    if db.query(User).filter(User.handle == payload.handle).first():
        raise HTTPException(status_code=409, detail="Handle already taken.")
    user = User(
        handle   = payload.handle,
        password = hash_password(payload.password),
        rank     = "DEADCAT",
        is_admin = False,
    )
    db.add(user); db.commit(); db.refresh(user)
    token = create_token({"sub": user.handle, "is_admin": False})
    return {"access_token": token, "token_type": "bearer", "user": user.to_dict()}

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.handle == payload.handle).first()

    if not user or not verify_password(payload.password, user.password):
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

    return TokenResponse(
        access_token=token,
        user=user.to_dict()
    )

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    """Returns the currently authenticated user's profile."""
    return current_user.to_dict()

@router.post("/logout")
def logout():
    """
    JWT is stateless — logout is handled client-side by deleting the token.
    This endpoint exists so the frontend has a clean logout call to make.
    """
    return {"message": "Logged out successfully"}