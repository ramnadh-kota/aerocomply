# Final Release Readiness (2026-09-30, branch `feature/post-freeze-productionization`)

Legend: PASS = implemented and verified in this repo. PARTIAL = works, known limits. NOT IMPLEMENTED.
EXTERNAL VALIDATION REQUIRED = cannot be proven from the repo.

| Area | Gate | Evidence / limit |
|---|---|---|
| Backend regression | PASS | 2225 passed, 0 failed, 16 deselected (full run, test DB) |
| Frontend | PASS | vitest 32 files / 352 tests; tsc clean; ESLint 0 errors; `next build` OK (100 pages) |
| Lint (ruff E9,F63,F7,F82) | PASS | clean on app, scripts, tests |
| Migrations 0062-0065 | PASS | up/down/up on scratch DB; head `0065` |
| Schema drift | PASS | 169 differences reviewed and pinned by guard test |
| Suite/Plan/Subscription entitlements | PASS | single resolver, no JWT claims, tested lifecycle |
| Tenant isolation | PASS | automated cross-tenant probe, mutation-tested |
| Concurrency | PASS | real parallel sessions (subscription lock, flight advisory lock, unique+SAVEPOINT) |
| Acquisition pipeline (CSV/JSON/MAVLink bytes/MQTT payload/DJI webhook) | PASS | 29 pipeline tests; HTTP push only |
| MAVLink over a physical link | EXTERNAL VALIDATION REQUIRED | harness ready; 12 bench tests pending hardware |
| MQTT broker / MAVLink socket listener | NOT IMPLEMENTED | HTTP push only |
| HUMS ingest -> exceedance -> finding -> M7 signal | PASS | dedup fixed for new data; legacy duplicates may exist |
| LISA entity resolution | PASS | tests; answer quality on real questions unvalidated |
| Browser (headless Chrome, CDP) | PASS | 44/44 checks, 0 console errors (scripted, not human UAT) |
| Customer UAT | EXTERNAL VALIDATION REQUIRED | |
| Billing (test provider) | PASS | lifecycle tests |
| Real payment provider | NOT IMPLEMENTED / EXTERNAL VALIDATION REQUIRED | test provider refused in production |
| Observability | PARTIAL | metrics + evidence-based health; in-process metrics, no tracing/dashboards |
| Security | PARTIAL | process-local rate limiting (auth + policy middleware), no MAVLink signature verification, no pen test |
| Background jobs / queue | NOT IMPLEMENTED | design in `PRODUCTION_RUNBOOK.md` |
| Retention / archival | NOT IMPLEMENTED | policy in `DATA_RETENTION_STRATEGY.md` |
| Performance | PARTIAL | 10k events OK at ~14-26 ev/s/worker; 100k not run (`PERFORMANCE_BENCHMARK.md`) |
| Production DB / deploy | EXTERNAL VALIDATION REQUIRED | never touched; preflight SQL + rollback guide provided |
| Helicopter / eVTOL suites | NOT IMPLEMENTED | scaffolding only |

## Blocking before a paid production launch
1. Run `backend/scripts/production_preflight.sql` on a production restore; fix FAILs.
2. Add a shared (proxy) rate limiter for multi-instance and decide on MAVLink signing.
3. Real payment provider (or launch without self-serve billing).
4. Capacity test on production-like hardware; profile per-event cost.
5. Physical MAVLink bench tests if MAVLink is sold.
