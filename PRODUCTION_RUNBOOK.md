# Production Runbook

Nothing here has been exercised in a production environment (EXTERNAL VALIDATION REQUIRED). The multi-process pieces
were exercised locally (`backend/scripts/e2e_listener_smoke.py`).

## Processes

| Process | Command | Scale | Notes |
|---|---|---|---|
| API | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (or the Docker image) | N instances behind the proxy | rate limits are per instance |
| Worker | `python -m app.worker --schedule` | ≥ 1 (parallel workers are safe: `SKIP LOCKED`) | runs `acquisition.ingest`, `acquisition.poll`, `retention.sweep`, `billing.dunning`; `--schedule` makes it enqueue the recurring jobs (idempotent across workers) |
| Listeners | `python -m app.listeners` | one supervisor per set of bind addresses (a port binds once) | UDP/TCP MAVLink, MQTT subscriber; reconciles data-source changes every 30 s; SIGTERM flushes buffers |

All share the same image and `DATABASE_URL`. Secrets come from `KOTA_SECRET_<reference>` environment variables. Run
migrations as a separate step (`alembic upgrade head`) before starting the new API — `/health/ready` returns 503
(`schema_mismatch`) until the database is at this build's head, so an early rollout is not routed traffic.

## Routine checks
| Check | How | Healthy |
|---|---|---|
| Liveness / readiness | `GET /health`, `GET /api/v1/health/ready` | 200; `schema.up_to_date: true` |
| Schema | `alembic current` | `0070` |
| Data integrity | `psql -f backend/scripts/production_preflight.sql` | no FAIL rows |
| Queue | `GET /api/v1/platform/jobs?status=DEAD` or `/health/ready` → `jobs` | dead = 0; `oldest_due_seconds` small |
| Metrics | `GET /api/v1/platform/metrics` | see OBSERVABILITY_ARCHITECTURE.md |
| Source health | Data Sources page / `kota_data_sources` | no FAILED |

## Deploy
1. Backup + `pg_restore --list` proof. 2. Preflight SQL. 3. `alembic upgrade head`. 4. Roll API, then workers, then
listeners. 5. Frontend build/ship. 6. Smoke: login, `/auth/me`, one ingest (sync and `?mode=async`), metrics scrape,
`/health/ready`. Rollback: `PRODUCTION_ROLLBACK_GUIDE.md`.

## Incidents
* **Telemetry not arriving.** Is the source ACTIVE? Data Sources page → `last_error`. A listener that refused to start
  says why (missing allow-list/signing, plaintext MQTT to a remote broker). Is the listener process up
  (`kota_listener_up` is only in its logs)? Is the worker draining (`/health/ready` → `jobs.oldest_due_seconds`)?
  `kota_listener_dropped_total{reason="backpressure"}` means workers cannot keep up: add workers.
* **Dead-lettered jobs.** `GET /platform/jobs?status=DEAD` shows `last_error`. Permanent errors (unknown/foreign
  source, bad OEM config, blocked SSRF target) need a config fix; then `POST /platform/jobs/{id}/requeue` (audited).
  Transient ones (OEM 5xx/429, network) already retried with backoff (5 s doubling to 15 min, ±25 %, 5 attempts).
* **A worker died mid-job.** The job stays RUNNING and returns to the queue after 10 minutes (stale reclaim); ingestion
  is idempotent (event ids), so a replay reports duplicates instead of double-counting.
* **OEM source not polling.** Needs `python -m app.worker --schedule` running; the scheduler ticks every 60 s, so the
  effective minimum interval is 60 s. `poll refused:` = permanent misconfiguration (see source `last_error`).
* **Signed MAVLink rejected.** `unsigned_rejected` / `bad_signature` / `replayed_signature` in the ingest report and the
  source `last_error`; check the key reference resolves (`KOTA_SECRET_…`) and the vehicle uses the same key/link id.
* **Customer sees "upgrade required" wrongly.** Entitlements resolve live from Suite → Plan → Subscription; inspect the
  subscription status/dates and plan features. A PAST_DUE subscription keeps access during the grace period; with
  `BILLING_ENFORCE_GRACE=true` the daily `billing.dunning` job cancels subscriptions past grace (audited, reversible).
* **Duplicate signals.** New data is deduplicated; legacy duplicates from before the fix may exist — close them in the
  app, do not bulk-delete customer data.
* **Rate-limited (429).** Policy name is in `kota_rate_limited_total`; tune with `RATE_LIMIT_OVERRIDES`.

## Retention (default OFF)
Policies are per organization or platform default, disabled until enabled, with floors (readings 30 d, event ledger 7 d,
jobs 1 d). `POST /platform/retention/run` is a dry run; deletion needs `RETENTION_DESTRUCTIVE_ENABLED=true` **and** an
enabled policy. Set `RETENTION_ARCHIVE_DIR` to archive (gzip JSONL, fsynced) before deleting. See
DATA_RETENTION_STRATEGY.md.

## Scaling path (not needed at current measured load)
The job interface (`job_service`: enqueue / claim / complete / fail) can be re-backed by Redis, SQS or Kafka without
changing handlers; listeners already only enqueue. For the shared rate limiter use the proxy or Redis.

## Known limits to communicate
MAVLink event time is arrival time; metrics are per-process; helicopter/eVTOL analytics are the shared deterministic
engine with operator-configured limits (no rotorcraft- or eVTOL-specific algorithms); 21 sample-data-only UI modules are
hidden from live organizations (KOTA_AEROSPACE_FINAL_SOFTWARE_GAP_MATRIX.md).
