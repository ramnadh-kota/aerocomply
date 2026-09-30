# Performance Benchmark

Tool: `backend/scripts/ingest_benchmark.py` (real HTTP, CSV_BATCH, 500 events/request, unique timestamps).
Target: local dev API (uvicorn, single process) + **scratch** Postgres DB (`aerocomply_m20_preview`), Windows laptop.
Not production hardware, not a load-balanced deployment. Treat as relative, not as capacity numbers.

| Events | Wall time | Events/s | Batch (500) p50 / p95 |
|---|---|---|---|
| 100 | 6.9 s | 14.4 | 6.9 s / 6.9 s (1 batch) |
| 1,000 | 54.2 s | 18.4 | 27.1 s / 15.9 s* |
| 10,000 | 376.9 s | 26.5 | 16.1 s / 43.8 s |
| 100,000 | **NOT RUN** (~1 h at this rate) | - | - |

\* percentiles over 2 batches are not meaningful. All events were accepted (0 loss, 0 duplicates).

Reads after 11,100 readings on one asset (median of 5): status 38 ms, latest 25 ms, history(limit 500) 19 ms,
flights 24 ms -> read APIs do not degrade at this size (indexed, bounded).

## Findings
1. **Ingest costs ~40-70 ms per event** (throughput rose from 14 to 26 ev/s as caches warmed, so part of the
   small-batch cost is fixed overhead). One worker sustains roughly 20-25 events/s. A single 10 Hz vibration
   stream per vehicle would saturate one worker at ~2-3 vehicles.
2. The design is correctness-first: per-event SAVEPOINT, asset/sensor resolution, flight advisory lock, reading
   insert, freshness/exceedance evaluation. The per-event query count was **not profiled** here; cause of the
   cost is therefore unverified. Suspects: per-event sensor/asset lookups, per-event exceedance evaluation, dev
   server (no `--workers`).
3. Not done (would be the next performance work): SQL statement counting per event (N+1 audit), bulk
   insert path for high-rate raw samples, multi-worker scaling test, 100k run, PostgreSQL tuning.
4. Mitigation available today without code: downsample at the gateway (send RMS/summary windows rather than raw
   10 Hz), run several API workers, keep batches <= 25 MB.

Verdict: functionally correct at 10k events; **capacity for high-rate fleets is PARTIAL / unproven** and must be
measured on production-like hardware (EXTERNAL VALIDATION REQUIRED).
