# DEADCATS Research Portal — Backend

FastAPI backend for the DEADCATS internal research platform.

---

## Stack

- **FastAPI** — API framework
- **PostgreSQL** — database
- **SQLAlchemy** — ORM
- **JWT** — authentication (python-jose)
- **bcrypt** — password hashing (passlib)

---

## Setup

### 1. Install PostgreSQL and create the database

```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres psql

# Inside psql:
CREATE USER deadcats WITH PASSWORD 'your_password';
CREATE DATABASE deadcats_db OWNER deadcats;
\q
```

### 2. Clone and install dependencies

```bash
git clone https://github.com/0xFrostyKen/DEADCATS_Researcher_Portal
cd DEADCATS_Researcher_Portal/backend
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual values:
#   DATABASE_URL
#   JWT_SECRET  (generate with: python -c "import secrets; print(secrets.token_hex(32))")
#   ADMIN_HANDLE + ADMIN_PASSWORD
#   FRONTEND_ORIGIN (your frontend origin, no trailing slash)
#   ALLOW_SELF_REGISTER (true/false)
#   REGISTER_TOKEN (required and should be long/random if self-register is enabled)
#   COOKIE_SECURE (true in HTTPS, false for local HTTP)
#   COOKIE_SAMESITE (strict|lax|none)
nano .env
```

### 4. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On first run the admin account is created automatically from your `.env` values.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/auth/login` | None | Login, returns JWT |
| GET | `/api/auth/me` | JWT | Current user info |
| POST | `/api/auth/logout` | JWT | Logout (client deletes token) |
| GET | `/api/users/` | JWT | List all members |
| POST | `/api/users/` | Admin | Create new member account |
| GET | `/api/users/{handle}` | JWT | Get member profile |
| PATCH | `/api/users/{handle}` | JWT | Update profile |
| POST | `/api/users/{handle}/reset-password` | JWT | Change password |
| DELETE | `/api/users/{handle}` | Admin | Disable account |
| GET | `/api/health` | None | Health check |
| GET | `/api/docs` | None | Swagger UI |

---

## Creating a new member (admin only)

```bash
curl -X POST http://localhost:8000/api/users/ \
  -H "Authorization: Bearer YOUR_ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "handle": "gh0stbyte",
    "password": "their_password",
    "emoji": "👻",
    "rank": "Paladin",
    "bio": "Binary exploitation specialist."
  }'
```

Or use the Swagger UI at `/api/docs` — much easier.

---

## Running on your laptop (production-ish)

```bash
# Install as a systemd service so it starts on boot
sudo nano /etc/systemd/system/deadcats.service
```

```ini
[Unit]
Description=DEADCATS Research Portal API
After=network.target postgresql.service

[Service]
User=your_user
WorkingDirectory=/path/to/backend
ExecStart=/usr/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/path/to/backend/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable deadcats
sudo systemctl start deadcats
```
