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
| `ENVIRONMENT` | recommended | `production` |
| `DEBUG` | recommended | `false` |
| `AI_PROVIDER` / `AI_BASE_URL` / `AI_MODEL` / `ANTHROPIC_API_KEY` | optional | Only if provider-backed Lisa reasoning is wanted. Deterministic Lisa (entity/reference resolution, orchestration, all MRO/Assessment tools) works with none of these set — it is not gated on an AI provider. |

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

## 5. Point the frontend at it

In Vercel's Project → Settings → Environment Variables, set:

```
NEXT_PUBLIC_API_BASE_URL=https://<your-backend-host>/api/v1
```

then redeploy the frontend (or trigger via a new commit to `main`).

## 6. Verify

```bash
curl https://<your-backend-host>/api/v1/health          # liveness only
curl https://<your-backend-host>/api/v1/health/ready     # also checks DB
```

Then in the deployed frontend, switch to REAL mode and confirm login
succeeds — that proves CORS, JWT, and DB connectivity all work end-to-end.

## What this backend does NOT need

- No message queue, no Redis, no background worker — every import/
  assessment run is synchronous request/response.
- No file storage — the CSV import pipeline stores validated rows as JSON
  on the `import_jobs` row, not the original file.
- No sticky sessions — JWTs are stateless; any number of replicas behind a
  load balancer work with no additional configuration.
