# Backend Production Deployment

This backend is a stateless FastAPI app + PostgreSQL. It has no built-in
deployment target — pick any host that can run a Docker image (or a plain
Python process) and reach a PostgreSQL instance. Render, Railway, Fly.io,
and AWS ECS/App Runner are all a reasonable fit; the `Dockerfile` in this
directory is unmodified between them.

## 1. Provision PostgreSQL

Use the host's managed Postgres (Render Postgres, Railway Postgres, RDS,
Supabase, Neon, etc.) — never point production at the local dev instance
under `.local-tools/`. Note the resulting connection string.

## 2. Environment variables

Copy `.env.example` and set real production values. Never commit the
result.

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+psycopg://user:pass@host:5432/dbname` |
| `JWT_SECRET_KEY` | yes | Long random secret. Rotating it invalidates all sessions. |
| `CORS_ALLOW_ORIGINS` | yes | JSON array of allowed origins, e.g. `["https://aerocomply.vercel.app"]` (see `.env.example`). |
| `ENVIRONMENT` | **required in practice** | `production` — see fail-fast guards below. |
| `DEBUG` | recommended | `false` |
| `AI_PROVIDER` / `AI_BASE_URL` / `AI_MODEL` / `ANTHROPIC_API_KEY` | optional | Only if provider-backed Lisa reasoning is wanted. Deterministic Lisa (entity/reference resolution, orchestration, all MRO/Assessment tools) works with none of these set — it is not gated on an AI provider. |

**Fail-fast production guards** (`app/main.py`): when `ENVIRONMENT` is set to
anything other than `development`, the app refuses to start (raises at
import time, before binding a port) if `JWT_SECRET_KEY` is still the
default placeholder, or if `DATABASE_URL` is still the default
local-development value — either would mean a misconfigured deploy
silently signs tokens with a public secret, or tries to reach a localhost
Postgres that doesn't exist in production. Leaving `ENVIRONMENT` unset (or
`development`) is what makes zero-config local dev work; this is also why
it is effectively required in any real deployment.

## 3. Build and deploy

```bash
docker build -t aerocomply-backend .
docker run -p 8000:8000 --env-file .env aerocomply-backend
```

Or point the host's native Python/Docker deploy at this repo's `backend/`
directory with the same Dockerfile.

## 4. Run migrations

Run once per deploy, against the same `DATABASE_URL` the app will use —
NOT automatically inside the container's `CMD` (see Dockerfile comment for
why):

```bash
alembic upgrade head
```

Confirm a single head afterward: `alembic heads` should print exactly one
revision.

## 5. Bootstrap the first Platform Admin

There is no public API endpoint for this — `PLATFORM_MANAGE` cannot be
self-granted (see `app/api/v1/platform.py`). Run once, against the
production `DATABASE_URL`:

```bash
DATABASE_URL=<production DATABASE_URL> python scripts/create_platform_admin.py \
    --email ops@yourcompany.com \
    --full-name "Platform Ops" \
    --password 'a-strong-password'
```

Safe to re-run — it exits without changes if that email already exists.
That platform admin can then create every subsequent customer organization
and its first admin through the normal `/api/v1/platform/*` API (the
`/platform/organizations` UI).

## 6. Point the frontend at it

In Vercel's Project → Settings → Environment Variables, set:

```
NEXT_PUBLIC_API_BASE_URL=https://<your-backend-host>/api/v1
```

then redeploy the frontend (or trigger via a new commit to `main`).

## 7. Verify

```bash
curl https://<your-backend-host>/api/v1/health          # liveness only
curl https://<your-backend-host>/api/v1/health/ready     # also checks DB
```

`/health/ready` returns quickly either way — the database engine has a
5-second `connect_timeout` (`app/db/session.py`), so an unreachable
database fails the probe in seconds rather than hanging for the
platform's default TCP timeout (verified manually: stopping Postgres
made `/health/ready` return HTTP 500 in ~5s, not hang).

Then in the deployed frontend, switch to REAL mode and confirm login
succeeds — that proves CORS, JWT, and DB connectivity all work end-to-end.

## 8. Secret management

- `JWT_SECRET_KEY` and `DATABASE_URL` are the only true secrets. Set them
  through the host's environment-variable/secrets mechanism (Render/
  Railway/Fly all have one) — never commit them, never put them in a
  Dockerfile `ENV`, never log them.
- `app/main.py` fails fast at startup outside `ENVIRONMENT=development` if
  either is still the local-dev placeholder — this is the backstop against
  an empty/misconfigured secret reaching production, not a substitute for
  actually setting them.
- Rotating `JWT_SECRET_KEY` invalidates every issued access/refresh token
  immediately (all users are signed out) — expected, not a bug.
- If `ANTHROPIC_API_KEY` is set, treat it with the same care; if unset,
  Lisa's deterministic tools/orchestration are unaffected (see `AI_PROVIDER`
  note above).

## 9. Backups / recovery

This repository does not provision or manage the database itself, so
backup/PITR behavior is entirely a property of whatever managed Postgres
is chosen — it is **not currently configured by anything in this repo**.
Before onboarding a real customer, confirm the chosen provider's backup
plan explicitly (e.g. Render/Railway/RDS/Supabase/Neon all offer managed
automated backups and point-in-time recovery on at least their paid
tiers) and document the actual retention window here once chosen. Treat
"no confirmed backup policy" as a genuine go-live blocker, not an
afterthought.

## 10. Rollback

- **Application code**: redeploy the previous image/commit through the
  host's normal deploy mechanism — the app is stateless, so this is safe
  at any time.
- **Database migrations**: each Alembic revision has a real `downgrade()`.
  To roll back one revision: `alembic downgrade -1` against the same
  `DATABASE_URL`. Review the specific migration's `downgrade()` first —
  several (e.g. `0023`, the aircraft-registration uniqueness constraint)
  will fail to re-apply forward if rolled-back-and-forward past data now
  violates a constraint that didn't exist before. Never run a downgrade
  against production without a recent backup restorable first (see §9).
- There is no automatic rollback-on-migration-failure — `alembic upgrade
  head` either fully succeeds or stops at the failing revision, leaving
  the schema at the last successful one; the app should not be pointed at
  a database mid-migration.

## What this backend does NOT need

- No message queue, no Redis, no background worker — every import/
  assessment run is synchronous request/response.
- No file storage — the CSV import pipeline stores validated rows as JSON
  on the `import_jobs` row, not the original file.
- No sticky sessions — JWTs are stateless; any number of replicas behind a
  load balancer work with no additional configuration.
