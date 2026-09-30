# Production Runbook

Nothing here has been exercised in a production environment. Commands are for operators with production access.

## Routine checks
| Check | How | Healthy |
|---|---|---|
| Liveness | `GET /health` | 200 (liveness only; does not test the DB) |
| Schema | `alembic current` | `0065` |
| Data integrity | `psql -f backend/scripts/production_preflight.sql` | no FAIL rows |
| Metrics | `GET /api/v1/platform/metrics` (platform token) | scrapes; see `OBSERVABILITY_ARCHITECTURE.md` |
| Source health | Data Sources page or `kota_data_sources` gauge | no FAILED |

## Deploy
1. Backup + `pg_restore --list` proof. 2. Run preflight SQL. 3. `alembic upgrade head`. 4. Roll out API.
5. Build/ship frontend. 6. Smoke: login, `/auth/me`, one ingest to a test source, metrics scrape. Rollback: `PRODUCTION_ROLLBACK_GUIDE.md`.

## Incidents
* **Customer sees "upgrade required" wrongly** - entitlements are resolved live from Suite -> Plan -> Subscription.
  Inspect the org's subscription status/dates and the plan's features; never patch the JWT. Baseline features
  (`audit_logging`, `release_readiness`) are always on.
* **Data source shows FAILED/INACTIVE** - health is evidence-based. Read `last_error`, `last_success_at`;
  FAILED = recent failures, INACTIVE = never/long silent. Check the sender, the source `ACTIVE` status, and
  the `system_id_map` (MAVLink) targets.
* **Telemetry "not arriving"** - ingest is an HTTP push (`POST /data-sources/{id}/ingest`). There is **no
  server-side MQTT/MAVLink socket listener process**; something must POST. Confirm the gateway is running.
* **Duplicate signals** - new data is deduplicated (UTC-normalized key). Legacy duplicates from before the fix
  may exist; resolve/close them via the app, do not bulk-delete customer data.
* **Billing** - if billing calls are refused in production, `BILLING_PROVIDER` is still `test` (deliberately refused).
  Configure a real provider (not yet implemented) or leave billing endpoints unused.

## Background jobs (Phase L status: NOT IMPLEMENTED)
There is no queue or worker process. Everything is request-scoped or computed on read. Consequences:
dunning retries, invoice emails, retention purges, stale-source alerts, and freshness sweeps need an external
scheduler (cron / Kubernetes CronJob) calling idempotent endpoints or scripts. Recommended design when built:
a single scheduler container running short idempotent tasks guarded by `pg_advisory_lock`, each writing a
row to an audit table; no in-process threads inside API workers.

## Known limits to communicate
No rate limiting (put it at the proxy); in-process metrics per worker; MAVLink event time = arrival time;
helicopter/eVTOL suites are scaffolding only.
