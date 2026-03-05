# DEADCATS Research Portal - Project Documentation

## 1. Overview
DEADCATS Research Portal is a full-stack internal security collaboration platform.

Main capabilities:
- Cookie/JWT auth with admin-managed accounts
- Research notes + foldering
- IOC tracking + export
- File vault with hashing and downloads
- Team announcements and credential drops
- Achievements/specializations/profile customization
- CTF planning/results/participation markers + reminders
- Personal bookmarks (notes + IOCs)
- Team whiteboard goals
- Admin panel and system monitor
- Optional background lofi player

Tech stack:
- Backend: FastAPI + SQLAlchemy
- DB: PostgreSQL
- Frontend: static HTML/CSS/JS (no build step)
- Auth: JWT in HttpOnly cookie (`dc_access_token`)

---

## 2. Repository Layout
Top-level:
- `backend/` - API server, models, routers, config, logs
- `assets/` - shared CSS/JS
- `partials/` - reusable navbar/footer/sidebar HTML fragments
- `*.html` - app pages (dashboard, admin, ctf, etc.)
- `profile_uploads/` - avatar/banner uploads
- `vault_files/` - uploaded vault files
- `music/` - optional lofi mp3 (`music/music.mp3`)
- `logs/` - runtime logs used by monitor/audit features

Backend internals:
- `backend/main.py` - app bootstrap, middleware, router registration, static mount
- `backend/core/config.py` - environment configuration
- `backend/core/security.py` - password hashing, token handling, auth dependencies
- `backend/models/*.py` - SQLAlchemy models
- `backend/routers/*.py` - feature routes

---

## 3. Setup (Local)

### 3.1 Prerequisites
- Python 3.11+ (project currently runs on 3.13 in your environment)
- PostgreSQL
- `pip` / virtualenv

### 3.2 Create DB
Example (PostgreSQL):
```sql
CREATE USER deadcats WITH PASSWORD 'change_me';
CREATE DATABASE deadcats_db OWNER deadcats;
```

### 3.3 Backend environment
Create/edit `backend/.env`:
```env
DATABASE_URL=postgresql://deadcats:change_me@localhost:5432/deadcats_db
JWT_SECRET=replace_with_32_plus_chars_random_secret
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480

ADMIN_HANDLE=admin
ADMIN_PASSWORD=change_me_admin_password
MASTER_HANDLE=deadcats_master333

FRONTEND_ORIGIN=http://127.0.0.1:8000

ALLOW_SELF_REGISTER=false
REGISTER_TOKEN=replace_with_long_random_token

COOKIE_SECURE=false
COOKIE_SAMESITE=lax

CTFTIME_TEAM_ID=367609
```

### 3.4 Install + run
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open:
- `http://127.0.0.1:8000/login.html`
- API docs: `http://127.0.0.1:8000/api/docs`

Notes:
- Backend mounts project root as static frontend (`/`).
- `Base.metadata.create_all()` runs at startup.
- A few schema safety `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...` statements run in lifespan.

---

## 4. Auth and Security Model
- Login sets HttpOnly cookie `dc_access_token`.
- API accepts cookie token first; bearer token fallback is also supported.
- Disabled users cannot authenticate.
- Admin-only operations use `require_admin` dependency.
- Master account (`MASTER_HANDLE`) has extra protections for admin account operations.

Registration controls:
- `ALLOW_SELF_REGISTER=false` (recommended): `/api/auth/register` blocked.
- `ALLOW_SELF_REGISTER=true`: still requires valid `REGISTER_TOKEN`.
- `REGISTER_TOKEN` must be secure (server enforces minimum security expectations).

Cookie guidance:
- Local HTTP: `COOKIE_SECURE=false`, `COOKIE_SAMESITE=lax`
- HTTPS prod: `COOKIE_SECURE=true`, usually `COOKIE_SAMESITE=strict`

Important:
- Editing `localStorage` values does not create accounts.
- Accounts are only created server-side via authenticated/validated API flows.

---

## 5. Frontend Modules
Pages:
- `index.html` - landing
- `login.html` - auth
- `dashboard.html` - team overview + notifications + reminders
- `admin.html` - admin operations
- `members.html` (+ `members/profile.html`) - member listing/profile
- `library.html` - notes
- `ioc-tracker.html` - IOC management
- `vault.html` - secure file vault
- `ctf.html` - CTF management + results
- `bookmarks.html` - user bookmarks
- `whiteboard.html` - team goals/config
- `monitor.html` - runtime monitor
- `pwnbox.html` - browser terminal workspace

Shared frontend assets:
- `assets/js/include.js` - partial loader
- `assets/js/dashboard.js` - dashboard logic + notifications + reminders
- `assets/js/lofi-player.js` - optional persistent lofi control
- `assets/css/base.css`, `theme-*.css`, `dashboard.css` - visual system

---

## 6. API Surface (By Router)

### Auth (`/api/auth`)
- `POST /register`
- `POST /login`
- `GET /me`
- `POST /logout`

### Users (`/api/users`)
- `GET /`
- `POST /` (admin)
- `GET /{handle}`
- `PATCH /{handle}`
- `POST /{handle}/reset-password`
- `POST /{handle}/avatar`
- `POST /{handle}/banner`
- `DELETE /{handle}` (admin, hard delete)

### Notes (`/api/notes`)
- `GET /folders`
- `POST /folders`
- `DELETE /folders/{folder_id}`
- `GET /`
- `POST /`
- `GET /{note_id}`
- `PATCH /{note_id}`
- `DELETE /{note_id}`

### IOCs (`/api/iocs`)
- `GET /`
- `POST /`
- `DELETE /{ioc_id}`
- `GET /export`

### Vault (`/api/vault`)
- `GET /`
- `POST /upload`
- `GET /download/{file_id}`
- `DELETE /{file_id}`

### Announcements (`/api/announcements`)
- `GET /`
- `POST /` (admin)
- `DELETE /{announcement_id}` (admin)

### Achievements (`/api/achievements`)
- `GET /`
- `POST /` (admin)
- `DELETE /{achievement_id}` (admin)
- `GET /user/{user_id}`
- `POST /user/{user_id}/assign` (admin)
- `DELETE /user/{user_id}/revoke/{achievement_id}` (admin)
- `POST /user/{user_id}/equip`
- `GET /user/{user_id}/specs`
- `POST /user/{user_id}/specs`
- `DELETE /user/{user_id}/specs/{spec_id}`
- `PATCH /user/{user_id}/profile`

### Bookmarks (`/api/bookmarks`)
- `GET /`
- `POST /`
- `DELETE /{bookmark_id}`

### Whiteboard (`/api/whiteboard`)
- `GET /config`
- `POST /config/reset` (admin)
- `GET /goals`
- `POST /goals`
- `PATCH /goals/{goal_id}`
- `DELETE /goals/{goal_id}`

### CTF (`/api/ctf`)
- `GET /proxy/team`
- `GET /proxy/upcoming`
- `GET /proxy/results/{year}`
- `GET /events`
- `PUT /events/{event_id}/marker`
- `DELETE /events/{event_id}/marker`
- `POST /events` (admin)
- `PATCH /events/{event_id}` (admin)
- `DELETE /events/{event_id}` (admin)
- `POST /events/{event_id}/result` (admin)
- `POST /events/{event_id}/participants` (admin)
- `DELETE /participants/{participant_id}` (admin)


### PwnBox (`/api/pwnbox`)
- `GET /health`
- `GET /status`
- `POST /start`
- `DELETE /stop`
- `WS /ws/{session_id}`

System endpoints:
- `GET /api/health`
- `GET /api/stats`
- `GET /api/monitor` (admin)

---

## 7. Data Model Summary
Main tables (selected):
- `users`
- `notes`, `folders`
- `iocs`
- `vault_files`
- `announcements`
- `achievements`, `user_achievements`, `user_specializations`
- `bookmarks`
- `team_goals`, `whiteboard_config`
- `ctf_events`, `ctf_results`, `ctf_participants`, `ctf_participation_markers`

Implementation note:
- No Alembic migration flow currently; startup uses create-all + targeted alter statements.

---

## 8. Storage Paths and Static Serving
- Profile images served from:
  - `/profile_uploads/{avatars|banners}/{filename}`
  - legacy alias: `/uploads/{folder}/{filename}`
- Vault files stored under `vault_files/`
- Music path for player: `/music/music.mp3`

Static serving protections (`SafeStaticFiles`):
- Blocks backend internals and hidden path traversal targets from direct static access.

---

## 9. Current Notable Behaviors
- Text wrapping safeguards exist for tags/badges to prevent overflow.
- User delete is permanent (not soft deactivate).
- Achievement creation can reflect correctly for creator profile workflows.
- CTF reminders notify users near 24h/1h windows when they marked "I Will Play".
- Lofi player is optional user-controlled UI audio.

---

## 10. Runbook (Ops Basics)

### Start service
```bash
cd backend
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Health checks
```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/stats
```

### Common log checks
- Auth/user issues: inspect API logs and `logs/auth.log`
- Admin actions: `logs/admin.log`
- Upload issues: `logs/uploads.log`
- IOC events: `logs/iocs.log`
- Alerts: `logs/alerts.log`

---

## 11. Troubleshooting

### "401 Unauthorized" for `/api/auth/me` on login page
Expected before login.

### `206 Partial Content` for `/music/music.mp3`
Expected for streamed/range audio requests.

### Avatar/banner uploads return 404 on fetch
Confirm files exist in `profile_uploads/avatars` or `profile_uploads/banners` and URL starts with `/profile_uploads/...`.

### CORS/cookie issues
- Ensure `FRONTEND_ORIGIN` matches actual origin exactly.
- Verify `COOKIE_SECURE` and `COOKIE_SAMESITE` for HTTP vs HTTPS.

### Registration not working
- Check `ALLOW_SELF_REGISTER`
- Ensure `REGISTER_TOKEN` is configured and sufficiently strong

### Music button visible but no sound
- Confirm browser tab not muted and system output device is correct
- Verify `music/music.mp3` exists and is readable
- Hard refresh after JS changes (`Ctrl+Shift+R`)

---

## 12. Production Recommendations
- Put app behind HTTPS reverse proxy (Nginx/Caddy)
- Set `COOKIE_SECURE=true`
- Use strong fixed `JWT_SECRET`
- Use strong `ADMIN_PASSWORD`
- Lock DB access to private network
- Add backup policy for database + `profile_uploads/` + `vault_files/`
- Add periodic dependency updates and security patching

---

## 13. Quick Feature Checklist
- [x] Auth/login/logout/me
- [x] Admin user create/edit/delete
- [x] Profile avatar/banner uploads
- [x] Notes + folders + tags
- [x] IOC tracker + severity + export
- [x] Vault upload/download/delete + SHA256 metadata
- [x] Announcements + creds board
- [x] Achievements + user specs
- [x] Bookmarks
- [x] Whiteboard team goals
- [x] CTF planning/results/participants/markers
- [x] Notifications + CTF reminders
- [x] Optional lofi playback


## 14. PwnBox Setup (Integrated)
PwnBox is integrated into the main backend and UI (`/pwnbox.html`).

Prerequisites:
- Docker daemon running on same host as backend
- Backend dependency `docker==7.1.0` installed

Install/update backend deps:
```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
```

Recommended env vars (optional, defaults shown):
```env
PWNBOX_IMAGE=pwnbox-base:latest
PWNBOX_WORKDIR=/home/hacker
PWNBOX_SESSION_TTL_MINUTES=90
PWNBOX_AUTO_BUILD=true
# Optional custom state path
# PWNBOX_STATE_FILE=/absolute/path/pwnbox_session_state.json
```

How it works:
- First `POST /api/pwnbox/start` checks if image exists.
- If missing and `PWNBOX_AUTO_BUILD=true`, backend auto-builds `pwnbox-base:latest`.
- Session is persisted to `backend/pwnbox_session_state.json` and reconciled on restart.
- Single global session only.

Run backend:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Use in portal:
- Login to portal
- Open `/pwnbox.html` (or Dashboard sidebar -> PwnBox)
- Click `Start`, then terminal attaches automatically

Troubleshooting:
- If start fails with Docker error: ensure `docker info` works for backend user
- If websocket fails: ensure backend runs with `uvicorn[standard]`
- If shell doesn’t attach: check backend logs for `/api/pwnbox/ws/*`

### 14.1 Collaborator Onboarding (Fresh Machine)
If someone clones your codebase on a new machine, use this sequence.

1. Clone and enter project:
```bash
git clone <repo-url>
cd DEADCATS_Researcher_Portal
```

2. Install Docker and verify daemon access:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker info
```

3. Start backend:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

4. Open portal:
- Login: `http://127.0.0.1:8000/login.html`
- PwnBox: `http://127.0.0.1:8000/pwnbox.html`

Notes:
- First PwnBox start may take longer because image auto-build runs once.
- If Docker is not configured, the rest of the portal still works; only PwnBox will fail.
