# Production Rollback Guide

Nothing here has been executed against production. Rehearse on a restored copy first.

## Principles
* Take a verified backup **before** every deploy (`pg_dump -Fc`, then `pg_restore --list` to prove it reads).
* Application rollback (previous image/commit) is safe and fast. Schema rollback is riskier - decide per migration.
* Never rewrite git history or move the frozen tag `KOTA-AEROSPACE-FORENSIC-VALIDATED-2026-09-30`.

## Application rollback
1. Stop routing traffic to the new version (or scale it to 0).
2. Redeploy the previous image / `git checkout <previous-release-commit>`.
3. Verify: `GET /health`, a login, `GET /api/v1/platform/metrics` scrape, one ingest to a test source.
Migrations 0062-0070 add tables/columns or correct drift. Older application code that predates a table simply
does not use it, so an app-only rollback normally needs no schema change (verify against the previous release
on a restored copy - not rehearsed). **Stop the worker and listeners before rolling the API back**, and drain or export
the job queue first: a rolled-back API cannot read jobs, and queued/dead jobs are lost by a downgrade of 0066.

## Schema rollback (Alembic)
Migrations round-trip (upgrade -> downgrade -> upgrade verified on a scratch DB).
```
alembic current
alembic downgrade 0069   # undo 0070 only
alembic downgrade 0064   # undo 0065-0070 (destroys jobs, retention policies, helicopter/eVTOL details, sensor limits)
alembic downgrade 0063   # also undo billing tables  (DESTROYS billing rows)
```
| Migration | Downgrade effect | Data loss |
|---|---|---|
| 0070 per-sensor HUMS limits | drops `warning_threshold` / `critical_threshold` on `hums_sensors` | configured OEM limits (sensors fall back to platform defaults; already-recorded exceedances keep their own threshold value) |
| 0069 `subscriptions.past_due_since` | drops the column | grace-clock start (recomputed from `updated_at` by the older code) |
| 0068 helicopter / eVTOL details | drops `helicopter_details`, `evtol_details` | airframe detail rows only (assets are untouched) |
| 0067 retention policies | drops `retention_policies` | policies only (all default to disabled); no customer data |
| 0066 background jobs | drops `background_jobs` | **queued, running and dead-letter jobs** and their raw payload bytes |
| 0065 schema drift corrections | restores previous constraints/types | none expected; re-check preflight SQL first |
| 0064 billing abstraction | drops plan_prices, invoices, payments | **all billing data** |
| 0063 acquisition health evidence | drops health-evidence columns on `data_sources` | health history |
| 0062 data sources / connector config | **drops the `data_sources` table** | **all data sources and their config** |

Before any downgrade that drops data: export the affected tables (`pg_dump -t ...`).

## Data restore
Point-in-time or full restore from the pre-deploy dump into a **new** database, validate with
`backend/scripts/production_preflight.sql`, then switch `DATABASE_URL`. Do not restore over the live DB
without an incident lead's sign-off.

## Decision table
| Symptom | Action |
|---|---|
| 5xx after deploy, schema unchanged | app rollback |
| Migration failed midway | Postgres DDL is transactional: it rolled back; fix and re-run, do not hand-edit `alembic_version` |
| Data corruption suspected | freeze writes, snapshot, restore to new DB |
| Wrong entitlements | not a rollback case: fix plan/subscription rows via platform API (audited) |
