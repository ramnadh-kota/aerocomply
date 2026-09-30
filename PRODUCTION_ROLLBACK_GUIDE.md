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
Migrations 0062-0065 add tables/columns or correct drift. Older application code that predates a table simply
does not use it, so an app-only rollback normally needs no schema change (verify against the previous release
on a restored copy - not rehearsed).

## Schema rollback (Alembic)
Migrations round-trip (upgrade -> downgrade -> upgrade verified on a scratch DB).
```
alembic current
alembic downgrade 0064   # undo 0065 only
alembic downgrade 0063   # also undo billing tables  (DESTROYS billing rows)
```
| Migration | Downgrade effect | Data loss |
|---|---|---|
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
