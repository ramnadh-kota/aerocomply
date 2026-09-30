# Performance Benchmark

Tools: `backend/scripts/ingest_benchmark.py` (real HTTP, `CSV_BATCH`, 500 events per request, unique timestamps) and
`backend/tests/integration/test_zz_ingest_profile.py` (in-process profile: SQL statements and CPU per event).
Target: one uvicorn worker on a Windows laptop, **scratch** PostgreSQL database (`aerocomply_bench`), API and database
on the same machine. These are relative numbers for this software path, **not capacity numbers for production hardware
(EXTERNAL VALIDATION REQUIRED)**.

## Result (after optimization)

| Events | Wall time | Events/s | Batch (500) p50 / p95 |
|---|---|---|---|
| 1 000 | 2.95 s | 339 | 1.5 s / 1.3 s |
| 10 000 | 48.6 s | 206 | 2.4 s / 3.0 s |
| **100 000** | **358.9 s** | **279** | 1.7 s / 2.4 s |

All events accepted (0 rejected, 0 duplicates). Read APIs after 111 000 readings on one asset (median of 5): status 20 ms,
latest 46 ms, history(limit 500) 37 ms, flights 17 ms — bounded and indexed, no degradation with volume.

Before: 14.4 / 18.4 / 26.5 events/s (100 / 1 000 / 10 000 events), 100 000 not attempted (~1 h).
Improvement ≈ 10–24× (23× at 1 000 events, 11× at 10 000; 100 000 was previously not attempted).

## Where the time went (profiled, 300 events in-process)

| Step | Before | After |
|---|---|---|
| ms per event | 39.5 | 5.5 |
| SQL statements per event | 25.0 | 6.6 |
| dominant cost | per-event HUMS feature extraction + baseline versioning (8 feature inserts, 1 baseline insert + update, ~20 statements) = 75 % of request time | one insert each for reading and event-ledger row, plus amortised evaluation |

Root causes and fixes (each with a regression test):
1. **HUMS evaluated on every event** although the health service's own contract says "once per ingested batch".
   Batch ingestion now evaluates each sensor every 10 new readings (half the 20-reading window, so every reading falls in
   an evaluated window) and once at the end; a mid-batch spike is still detected (`test_mid_batch_vibration_spike_…`,
   mutation-checked). Single-event callers keep per-event evaluation.
2. **Repeated identical lookups** (asset mapping → asset → sensor for every row of a batch): batch-scoped cache; nothing
   created inside a SAVEPOINT is cached until the event succeeds (`test_a_sensor_created_by_a_failed_event_…`).
3. **One immutable audit row per telemetry event** (unbounded, unpurgeable): batches now write one summary audit row;
   per-event provenance stays in `telemetry_event_logs`.

## Remaining limits (honest)
* ≈ 200–340 events/s per API worker on this laptop. One 10 Hz sensor per vehicle is 10 ev/s, so a worker carries
  roughly 20–30 such streams; scale with workers (jobs are `SKIP LOCKED`, listeners only enqueue).
* Not done: multi-worker scaling test and PostgreSQL tuning on production-like hardware; bulk-insert path for very
  high-rate raw samples (the remaining per-event cost is two single-row INSERTs inside a SAVEPOINT).
* `hums_features` dominates storage (≈ 1.4 KB/row): see DATA_RETENTION_STRATEGY.md.

Reproduce: create a scratch database, `alembic upgrade head`, start the API, seed an org with a CSV_BATCH source, then
`python -m scripts.ingest_benchmark --api … --sizes 1000 10000 100000 --batch 500`.
