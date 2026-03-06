# DEADCATS Research Portal

DEADCATS is a full-stack cyber research portal with:

- Team dashboard, announcements, notes, vault, whiteboard, members, CTF tracking
- Auth + admin portal + profile management
- Integrated **PwnBox** browser terminal (`/pwnbox.html`)
- PostgreSQL backend (FastAPI + SQLAlchemy)

This README is the single source of truth for setup and deployment.

## Tech Stack

- Backend: FastAPI, SQLAlchemy
- DB: PostgreSQL
- Frontend: Static HTML/CSS/JS served by FastAPI
- PwnBox runtime: Docker SDK + host Docker daemon

## Quick Start (Docker, Recommended)

This guide uses `docker-compose` (legacy CLI). If your machine has Compose v2 plugin, you can replace it with `docker compose`.

### 1) Clone and enter repo

```bash
git clone <your-repo-url>
cd DEADCATS_Researcher_Portal
```

### 2) Create env file

```bash
cp .env.example .env
```

Edit `.env` and set secure values (especially `JWT_SECRET`, `ADMIN_PASSWORD`).

### 3) Start everything

```bash
docker-compose up -d --build
```

Expected output includes:
- `Container deadcats-db ... Healthy`
- `Container deadcats-app ... Started`

### 4) Open app

- `http://127.0.0.1:8000/login.html`
- `http://127.0.0.1:8000/dashboard.html`
- `http://127.0.0.1:8000/pwnbox.html`

### 5) Logs / status

```bash
docker-compose logs -f app
docker-compose ps
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/pwnbox/health
```

You should see startup lines like:
- `Admin account 'deadcats_master333' created.`
- `Uvicorn running on http://0.0.0.0:8000`

### 6) Stop

```bash
docker-compose down
```

To also delete DB data:

```bash
docker-compose down -v
```

Full reset (including all project volumes + orphan containers):

```bash
docker-compose down -v --remove-orphans
docker-compose up -d --build
```

## What Docker Compose Brings Up

- `db`: PostgreSQL 16
- `app`: FastAPI app serving API + all frontend pages

`app` mounts `/var/run/docker.sock`, so PwnBox can create user containers on the host Docker daemon.

## Environment Variables (`.env`)

Minimum recommended:

```env
POSTGRES_USER=deadcats
POSTGRES_PASSWORD=change_me
POSTGRES_DB=deadcats_db

JWT_SECRET=replace_with_a_long_random_secret_at_least_32_chars
ADMIN_HANDLE=deadcats_master333
ADMIN_PASSWORD=change_me_now

FRONTEND_ORIGIN=http://127.0.0.1:8000
ALLOW_SELF_REGISTER=false
REGISTER_TOKEN=
COOKIE_SECURE=false
COOKIE_SAMESITE=lax

PWNBOX_IMAGE=pwnbox-base:latest
PWNBOX_AUTO_BUILD=true
PWNBOX_SESSION_TTL_MINUTES=90
```

Notes:

- `COOKIE_SECURE=true` only when using HTTPS.
- If `PWNBOX_AUTO_BUILD=true`, first PwnBox start builds base image automatically.

## Common Commands

Rebuild app:

```bash
docker-compose up -d --build app
```

Restart app only:

```bash
docker-compose restart app
```

See DB logs:

```bash
docker-compose logs -f db
```

Run DB shell:

```bash
docker-compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

## Local Non-Docker Run (Optional)

Requirements:

- Python 3.11+
- PostgreSQL running locally
- Docker running locally (for PwnBox)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## PwnBox Behavior

- Single active session at a time
- Session lock/state persisted on backend side
- Web terminal over WebSocket
- User shell inside isolated container
- Owner/admin protection for attach/stop paths
- First run may take ~1-3 minutes while base image is prepared

When clicking `Start` in `/pwnbox.html`:

- `POST /api/pwnbox/start 201` = new PwnBox session created
- `POST /api/pwnbox/start 409` = session already active (UI reconnects to active session)
- WebSocket log `... /api/pwnbox/ws/<session_id> [accepted]` = terminal attached successfully

If PwnBox start fails:

1. Confirm Docker socket mount is present (`/var/run/docker.sock` in app container).
2. Check app logs:
   ```bash
   docker-compose logs -f app
   ```
3. Verify API:
   ```bash
   curl -s http://127.0.0.1:8000/api/pwnbox/status
   ```

Optional live checks while waiting:

```bash
docker images | grep pwnbox-base
```

## Persistence

Compose volumes persist:

- PostgreSQL data
- `profile_uploads`
- `vault_files`
- `logs`

## Security Notes

- Set strong `JWT_SECRET` and `ADMIN_PASSWORD`.
- Use HTTPS + reverse proxy in production.
- Set `COOKIE_SECURE=true` under HTTPS.
- Limit host access to Docker socket (high-privilege surface).

## Project Layout

- `backend/` - FastAPI app, routers, models
- `assets/` - shared frontend JS/CSS
- `partials/` - shared page partials
- `*.html` - frontend pages
- `pwnbox/` - legacy standalone PwnBox scaffold/scripts

Primary production path is integrated app at `/pwnbox.html` via main backend.
