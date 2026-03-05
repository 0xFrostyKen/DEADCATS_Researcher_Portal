from dotenv import load_dotenv
import os
import secrets
import sys

load_dotenv()

DATABASE_URL      = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required.")

_jwt_secret_env = os.getenv("JWT_SECRET")
if not _jwt_secret_env or _jwt_secret_env == "changeme":
    JWT_SECRET = secrets.token_urlsafe(48)
    print("[SECURITY] JWT_SECRET was missing or insecure; generated an ephemeral secret for this process.", file=sys.stderr)
else:
    JWT_SECRET = _jwt_secret_env
JWT_ALGORITHM     = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES= int(os.getenv("JWT_EXPIRE_MINUTES", 480))
ADMIN_HANDLE      = os.getenv("ADMIN_HANDLE", "admin")
_admin_password_env = os.getenv("ADMIN_PASSWORD")
if not _admin_password_env or _admin_password_env == "changeme":
    ADMIN_PASSWORD = secrets.token_urlsafe(18)
    print(f"[SECURITY] ADMIN_PASSWORD was missing or insecure; generated bootstrap password: {ADMIN_PASSWORD}", file=sys.stderr)
else:
    ADMIN_PASSWORD = _admin_password_env
FRONTEND_ORIGIN   = os.getenv("FRONTEND_ORIGIN", "http://localhost:5500")
REGISTER_TOKEN    = os.getenv("REGISTER_TOKEN", "")
ALLOW_SELF_REGISTER = os.getenv("ALLOW_SELF_REGISTER", "false").strip().lower() in {"1", "true", "yes", "on"}
COOKIE_SECURE     = os.getenv("COOKIE_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
COOKIE_SAMESITE   = os.getenv("COOKIE_SAMESITE", "lax").strip().lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    COOKIE_SAMESITE = "lax"
MASTER_HANDLE     = os.getenv("MASTER_HANDLE", "deadcats_master333")
CTFTIME_TEAM_ID   = os.getenv("CTFTIME_TEAM_ID", "367609")

if len(JWT_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must be at least 32 characters.")
