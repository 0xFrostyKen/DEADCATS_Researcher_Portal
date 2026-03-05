# DEADCATS Security/Auth Notes

## Registration Security

- Self-registration is controlled by `ALLOW_SELF_REGISTER`.
  - `false` (recommended): `/api/auth/register` is blocked.
  - `true`: registration is allowed, but still requires a valid access token.

- `REGISTER_TOKEN` must be securely configured.
  - Minimum length: **16 characters**.
  - Recommended: **32+ random characters**.
  - If too short/insecure, backend returns:
    - `Registration token is not configured securely.`

## Environment Variables (backend/.env)

Use these values (adjust for your environment):

```env
FRONTEND_ORIGIN=http://localhost:5500
ALLOW_SELF_REGISTER=false
REGISTER_TOKEN=<long-random-token>
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
```

Production guidance:
- Set `COOKIE_SECURE=true` when using HTTPS.
- Prefer `COOKIE_SAMESITE=strict` unless you need cross-site behavior.

## Important Clarification

Changing browser local storage (for example, setting `dc_user`) does **not** create accounts.
Account creation only happens on backend `/api/auth/register` after server-side checks pass.
