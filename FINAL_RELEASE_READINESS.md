# Final Release Readiness (verified 2026-10-01, branch `feature/post-freeze-productionization`)

**SOFTWARE IMPLEMENTATION: COMPLETE. SOFTWARE-COMPLETABLE GAP COUNT: 0. EXTERNAL VALIDATION: PENDING** (physical drone/aircraft/autopilot testing, real telemetry-source validation, real MAVLink/RF validation, real MQTT/OEM/DJI environments where applicable, production-scale infrastructure validation, payment-provider validation where applicable, customer UAT, external penetration testing; none performed, none claimed). See `KOTA_AEROSPACE_FINAL_SOFTWARE_GAP_MATRIX.md`.

Legend: PASS = implemented and verified in this repo. PARTIAL = works, known limits. OPEN = software work remaining (none at this date).
EXTERNAL = cannot be proven from the repo. Detail: `KOTA_AEROSPACE_FINAL_SOFTWARE_GAP_MATRIX.md`.

| Area | Gate | Evidence / limit |
|---|---|---|
| Backend regression | PASS | 2690 passed, 0 failed, 0 skipped, 16 deselected (full run, scratch DB, 478 s, 2026-10-01) |
| Frontend | PASS | vitest 37 files / 383 tests; `tsc` clean; ESLint 0 errors; `next build` OK |
| Lint (ruff E9,F63,F7,F82) | PASS | clean on app, scripts, tests |
| Migrations 0062-0070 | PASS | up/down/up 0070 -> 0065 -> 0070 on a scratch DB; head `0070` |
| Entitlements (Suite/Plan/Subscription) | PASS | one resolver; router-level gates; DB-authoritative auth |
| Tenant isolation | PASS | cross-tenant probes; foreign facility/asset ids rejected |
| Concurrency | PASS | real parallel sessions incl. HUMS exceedance advisory lock, M7 signal adopt-winner |
| Acquisition (CSV/JSON/MAVLink/MQTT/webhook/OEM) | PASS | server-side listeners, PostgreSQL job queue, retries, dead-letter |
| MAVLink-2 signing, webhook HMAC, SSRF guard | PASS | unit + API tests |
| Retention | PASS | default OFF, dry-run default, archive-before-delete |
| Helicopter / eVTOL suites | PASS | details tables, services, API, UI, HUMS templates, journeys (no rotor/eVTOL-specific analytics: needs OEM data) |
| LISA | PASS | 61 tools, 261-case matrix |
| Rate limiting | PASS (software) | in-memory + shared Redis backends, fail-closed for sensitive policies; a real Redis is EXTERNAL VALIDATION |
| Performance | PARTIAL | 100k benchmark: ~279 ev/s single worker, HTTP push (`PERFORMANCE_BENCHMARK.md`) |
| Browser (headless Chrome, CDP) | PASS | 44/44, 56/56, 42/42, 0 console errors (scripted, not human UAT) |
| Sample-data pages in live sessions | OPEN (G1) | 21 sample-only routes are hidden/redirected from live sessions but have no live build; each needs a build-or-retire decision |
| MAVLink over a physical link / serial listener | EXTERNAL | hardware |
| Customer UAT | EXTERNAL | |
| Real payment provider | EXTERNAL | test provider refused in production |
| Production DB / deploy / pen test | EXTERNAL | never touched; preflight SQL + rollback guide provided |

## Before a paid production launch
1. Run `backend/scripts/production_preflight.sql` on a production restore.
2. Shared rate limiter for multi-instance.
3. Real payment provider, or launch without self-serve billing.
4. Capacity test on production-like hardware.
5. Physical MAVLink bench tests if MAVLink is sold.
6. Decide G1 (build or retire the 21 sample-only pages).
