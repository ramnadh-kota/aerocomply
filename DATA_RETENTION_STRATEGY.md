# Data Retention (as implemented, 2026-09-30)

Retention is **implemented and OFF by default**: nothing is ever purged unless a policy row exists, is enabled, and the
deployment sets `RETENTION_DESTRUCTIVE_ENABLED=true`. Code: `app/services/retention_service.py`,
`app/models/retention.py` (migration 0067), `app/retention.py` (CLI), job `retention.sweep`, API under
`/api/v1/platform/retention/*`. Tests: `test_retention.py` (10).

## What can be purged
| Class | Table | Eligible rows | Floor | Never purged |
|---|---|---|---|---|
| `TELEMETRY_READINGS` | `hums_sensor_readings` | older than the cutoff | 30 days | readings inside any recorded exceedance window (the evidence for a finding) |
| `TELEMETRY_EVENT_LOG` | `telemetry_event_logs` (idempotency / provenance ledger) | any status except QUARANTINED, older than the cutoff | 7 days | quarantined events (still awaiting triage/replay) |
| `BACKGROUND_JOBS` | `background_jobs` | SUCCEEDED/CANCELED older than the cutoff; DEAD older than max(cutoff, 30 days) | 1 day | QUEUED / RUNNING jobs, recent dead-letters |
| `HUMS_FEATURES` | `hums_features` (derived; the largest table per ingested event) | older than the cutoff | 30 days | the newest 100 rows per (sensor, feature type) — baselines and prognostics are computed from recent history — and any feature window that backs a recorded exceedance |

`audit_events` are immutable (database trigger) and are never purged. Findings, evidence, exceedances, work orders,
compliance records, invoices and payments are not covered by any policy: their retention is a legal/customer decision.
Note: deleting old ledger rows means a duplicate of a very old event could be re-ingested once; choose a horizon longer
than any realistic redelivery window.

## Safety rules (each tested)
* No policy, or a disabled one → no-op. Tenant policy overrides the platform default; a tenant can opt out.
* `dry_run` (default in the API, CLI and job) only counts what would be removed.
* Real deletion needs the deployment switch **and** `dry_run=false` (or `--execute`); otherwise HTTP 409 / refusal.
* A policy below the class floor is refused when set and clamped at run time (a hand-edited row cannot undercut it).
* Execution is per tenant (never a cross-tenant sweep); deletion is batched (5 000 ids).
* Optional archive-before-delete: with `RETENTION_ARCHIVE_DIR`, each batch is written as gzip JSONL under
  `<dir>/<organization>/<class>/`, `fsync`ed, and only then deleted. If the archive write fails, that batch is not deleted
  and the error is reported in the result.
* Every purge that deletes rows writes a `retention.purged` audit event; policy changes write `retention.policy_set`
  (platform-default policies are audited under the acting operator's organization).

## Operating it
```
PUT  /api/v1/platform/retention/policies   {"organization_id": null|uuid, "data_class": "...", "retention_days": 90, "enabled": true}
POST /api/v1/platform/retention/run?dry_run=true[&organization_id=...]
python -m app.retention            # dry run (cron)      python -m app.retention --execute
python -m app.worker --schedule    # enqueues retention.sweep daily; executes only if the deployment switch is on
```

## Sizing guidance
Measured on the scratch database after 111 000 single-reading events (heap + indexes): readings 370 B/row (39 MB),
event ledger 821 B/row (87 MB), HUMS features ≈ 1.4 KB/row (126 MB for 88 900 rows; batch evaluation writes about 0.8
feature rows per event). **≈ 2.3 KB per ingested event in total → ≈ 2.3 GB per million events.** One vehicle streaming one
10 Hz sensor is 864 000 events/day ≈ 2 GB/day, which is why the feature and ledger tables — not just raw readings — have
retention classes. Downsample at the gateway (send window statistics rather than raw samples) and enable retention.
Partitioning `hums_sensor_readings` by month is the next step if a single tenant exceeds hundreds of millions of rows
(NOT built).

## Tenant deletion
Organization deletion is a separate, pre-existing platform workflow (`deletion_service`: request → review → permanent
delete by a platform operator); retention never deletes a tenant.
