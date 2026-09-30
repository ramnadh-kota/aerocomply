# Data Retention Strategy

Status: **policy and sizing guidance only. No automated purge/archival exists** (NOT IMPLEMENTED; needs the
scheduler described in `PRODUCTION_RUNBOOK.md`). Customer data is never deleted by application code today.

## Growth drivers
Measured on a dev DB: ~15.7k `hums_sensor_readings` = 6.6 MB (about 0.4 KB/row incl. indexes);
`telemetry_event_logs` ~ 1 row per ingested event (row size not measurable from a 51-row sample -
re-measure on real traffic; the benchmark below covers up to 10k events). Rough planning: 1 vehicle x 10 Hz vibration = 864k readings/day ~ 350 MB/day/vehicle
before compression. **This is why raw high-rate data must be tiered.**

## Proposed tiers (decide with customers/regulators; regulatory minimums override)
| Data | Hot (indexed) | Warm | Then |
|---|---|---|---|
| Raw readings (`hums_sensor_readings`) | 90 days | aggregated features/baselines kept | archive to object storage as Parquet, then drop partitions |
| `telemetry_event_logs` (dedup ledger) | 90 days | - | delete only rows older than the dedup horizon; late-duplicate risk beyond it is acceptable |
| Exceedances, findings, evidence, work orders | indefinite | - | airworthiness/audit records: follow customer's record-retention obligation (often >= 5-7 yrs) |
| Audit logs | >= 1 yr hot | - | archive; never edit |
| Invoices/payments | per tax law | - | keep |

## Mechanism (recommended, not built)
1. Convert `hums_sensor_readings` to monthly range partitions (by reading time) - new migration, tested on a copy.
2. Scheduler job: create next partition; detach + archive partitions past retention; log each action.
3. Keep derived features/exceedances so history stays explainable after raw data is archived.
4. Per-organization overrides only through a reviewed setting, never ad hoc SQL.

## Preconditions before enabling deletion
Verified restore of the archive, legal sign-off on periods, dry-run report of rows affected, and tenant-scoped
execution (no cross-tenant sweeps).
