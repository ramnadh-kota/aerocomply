# Kota Aerospace — Final Software Gap Matrix

Source of truth: the repository at branch `feature/post-freeze-productionization`, verified by tests (not by earlier
reports). Statuses: `COMPLETE`, `PARTIAL`, `MISSING`, `BROKEN`, `MOCKED`, `ASPIRATIONAL`, `EXTERNAL_ONLY`.
"Software?" = can the missing work be done and tested locally without hardware, credentials or production.

## Status terminology (authoritative)

| Dimension | Status |
|---|---|
| SOFTWARE IMPLEMENTATION | COMPLETE |
| SOFTWARE-COMPLETABLE GAP COUNT | 0 |
| EXTERNAL VALIDATION | PENDING (not performed, not simulated, not claimed) |

EXTERNAL VALIDATION REQUIRED:
- physical drone / aircraft / autopilot telemetry
- real MAVLink hardware and RF validation
- real MQTT / OEM / DJI environments where applicable
- production-scale infrastructure validation
- payment-provider validation where applicable
- customer UAT
- external penetration testing

The absence of physical hardware or external environments is not a software gap. The software is verified through
deterministic simulators, fixtures, synthetic telemetry, protocol test vectors and local integration environments; those
results demonstrate software behaviour only and are not evidence of field or hardware validation.

## Result (authoritative; reconciled 2026-10-01 at commit 070ce57 + this docs edit)

**AUTHORITATIVE SOFTWARE GAP COUNT: 0.** This file is the single authoritative gap matrix; the completion report and
FINAL_RELEASE_READINESS.md defer to it. Evidence of the final run: backend 2690 passed / 0 failed / 0 skipped
(16 deselected `real_storage`), vitest 383 passed / 37 files, `tsc` clean, ESLint 0 errors, `next build` OK, migration
round trip 0070 -> base -> 0070 on a fresh scratch DB, browser 44 + 56 + 42 + 25 (all pass) and a sample-data leak scan
of 132 routes x 2 organizations (clean).

Classification of every row that was previously open or partial:

| # | Item | Class | Evidence |
|---|------|-------|----------|
| G1 | 34 sample-only routes must never show sample data to a live session | CLOSED | `lib/mock-only-routes.ts` (24 live redirects, 10 notices), `tests/mock-only-routes.test.ts`, browser validate4 25/25, validate5 leak scan clean |
| G1-scope | Live backends/pages for the 10 notice-only routes (`/automation`, `/finance`, `/finance/[id]`, `/maintenance/projects/[id]`, `/maintenance/projects/[id]/intelligence`, `/organization/readiness`, `/pilot`, `/reports`, `/reports/[id]`, `/workspace`) | PRODUCT DECISION, not counted | These are not defects: they are labelled "Not connected to live data", leak nothing and render samples only in Demo mode. Whether to build or retire them is a roadmap decision that cannot be inferred from the architecture. If the product owner requires them live, each becomes a new software item. |
| RL | Rate limiting was process-local | CLOSED | `RateLimiter` protocol, in-memory + Redis backends, fail-closed policies; `tests/unit/test_rate_limiter_backends.py` (8), `test_rate_limit_policies.py`. Running Redis shared across instances = EXTERNAL |
| KG | Knowledge graph architecture | CLOSED (documented decision) | PostgreSQL only; `services/knowledge_graph.py` (+ `GraphRepository` seam), `digital_twin_service`; `test_knowledge_graph.py` (8), `test_digital_twin.py`; `docs/AEROSPACE_INTELLIGENCE_GRAPH.md` (`neo4j_*` settings are unused) |
| OBS | Exporter/monitoring integration | CLOSED | `core/metrics.py`, `core/metrics_server.py`, readiness checks; `test_observability.py`. Vendor dashboards are not required |
| MIG | Migration round trip | CLOSED | clean scratch DB: head 0070, base, head 0070 (96 tables / 434 indexes / 390 constraints). Caveat: downgrading 0047 over existing non-task evidence rows fails by design |
| REG | Full backend/frontend/lint/build/browser re-run | CLOSED | numbers above, all run 2026-10-01 |
| DOC | Stale test counts | CLOSED | counts updated in this file, the report and FINAL_RELEASE_READINESS.md |

Verification gaps: none open. Note that tenant isolation, security and customer-journey results are demonstrated by
test suites rather than a dedicated run: `test_tenant_isolation*.py`, `test_security_hardening`,
`test_customer_journey_{drone,airframes}`, `test_customer_journeys_commercial`, and
`test_customer_journey_platform_e2e.py` (Platform Admin -> suite -> plan -> org -> subscription -> user -> asset ->
data source -> telemetry -> HUMS -> M7 -> LISA -> audit, parametrised over AIRCRAFT, DRONE_UAV, HELICOPTER, EVTOL_AAM),
all inside the 2690 passed.

EXTERNAL validation only (never counted as software gaps): physical MAVLink/serial/RF and a real autopilot signer,
real DJI/OEM/MQTT-broker credentials, real payment provider, shared Redis across instances, production-scale
infrastructure and multi-worker scaling, OEM-specific rotor/eVTOL analytics data, customer UAT, penetration test, LISA
answer quality on real questions.

A serial-port MAVLink listener is not built: it needs `pyserial` and a physical device, and serial radios are normally
bridged to UDP/TCP by the gateway host (`mavlink-router` or `app/services/edge/gateway_service.py`).

## Commercial architecture

| Area | Capability | Status | Evidence | Missing work | Software? | Priority | Tests |
|---|---|---|---|---|---|---|---|
| Entitlements | Suite → Plan → Subscription → Feature/Limit/Override, single resolver, no JWT claims | COMPLETE | `entitlement_service.resolve_entitlements` | — | yes | — | `test_entitlement_resolution`, `test_m20_*`, `test_lisa_tool_matrix` |
| Entitlements | One current subscription per org per suite; multi-suite | COMPLETE | `subscription_service` row lock | — | yes | — | `test_concurrency` (6 parallel creators → 1) |
| Entitlements | No cross-suite leakage | COMPLETE | `is_feature_allowed_for_suite`, `require_feature` | — | yes | — | `test_airframes`, `test_customer_journeys_commercial` |
| Billing | Prices, invoices, payments, refunds, idempotent renewal | COMPLETE (test provider) | `billing_service` | Real provider | provider = EXTERNAL_ONLY | — | `test_billing_lifecycle` |
| Billing | Payment failure → PAST_DUE, exact grace clock, audited grace-expiry cancellation (opt-in) | COMPLETE | `past_due_since` (0069), `enforce_grace_expiry`, `billing.dunning` job | — | yes | — | `test_billing_lifecycle` (grace tests) |
| Billing | Live payment collection | EXTERNAL_ONLY | test provider refused in production | credentials | no | — | — |

## Suites

| Area | Capability | Status | Evidence | Missing work | Software? | Priority | Tests |
|---|---|---|---|---|---|---|---|
| Aircraft | fleet, flights, maintenance, WO, inspections, compliance, AOG, release readiness | COMPLETE | pre-existing modules | — | yes | — | existing suite |
| Drone | fleet, missions, flights, batteries, telemetry, HUMS, M7, LISA | COMPLETE | `drones.py`, acquisition pipeline | — | yes | — | `test_customer_journey_drone` |
| Helicopter | asset + rotor-system details, components (rotor/transmission/engine), flight hours & cycles, maintenance, lifecycle, HUMS starter sensors, per-sensor limits, UI, entitlement gate | COMPLETE | `airframes.py`, `airframe_service`, `hums_templates`, migration 0068/0070 | Rotor-specific analytics (track & balance, gearbox condition indicators) need OEM data | analytics = EXTERNAL_ONLY | — | `test_airframes`, `test_customer_journey_airframes`, browser 53/53 |
| eVTOL/AAM | asset + propulsion/HV details, batteries, components, hours & cycles, HUMS starter sensors (voltage/current/temperature/vibration), UI | COMPLETE | same | Propulsor-efficiency / thermal models need OEM data | EXTERNAL_ONLY | — | same |
| Suites | Generic `/assets` no longer a side door around a family's entitlement | COMPLETE | `assets.py` `_FAMILY_FEATURE` | — | yes | — | `test_generic_assets_endpoint_is_not_a_side_door` |

## Data acquisition and infrastructure

| Area | Capability | Status | Evidence | Missing work | Software? | Priority | Tests |
|---|---|---|---|---|---|---|---|
| MAVLink | v1/v2, CRC_EXTRA, sysid/compid, sequence, dup, late, loss, multi-vehicle | COMPLETE | `mavlink_connector` | — | yes | — | `test_m20_mavlink_integrity` |
| MAVLink | v2 signature verification, replay protection, fail-closed | COMPLETE | `_verify_signature`, `secrets` | Cross-check with a real autopilot signer | interop = EXTERNAL_ONLY | — | `test_mavlink_signing`, `test_mavlink_signing_api` |
| MAVLink | UDP and TCP listeners (allow-list and/or signing required, back-pressure, connection cap, idle timeout) | COMPLETE | `listeners/udp_mavlink.py`, `tcp_mavlink.py` | — | yes | — | `test_listeners` (real sockets), `scripts/e2e_listener_smoke.py` (separate processes) |
| MAVLink | Serial-port listener | EXTERNAL_ONLY | needs a device and `pyserial`; radios are bridged to UDP/TCP | hardware | no | — | bench harness supports `serial:` sources |
| MAVLink | Physical link behaviour, RF, real autopilot | EXTERNAL_ONLY | bench harness + plan | hardware | no | — | `scripts/mavlink_bench_harness.py` |
| MQTT | subscribe, filter, reconnect+backoff, TLS/plaintext policy, secret password | COMPLETE | `listeners/mqtt.py`, in-memory broker (test double) | Real broker validation | broker = EXTERNAL_ONLY | — | `test_listeners` |
| DJI | HMAC-signed webhook, fail closed | COMPLETE | `telemetry.py` | Real FlightHub | EXTERNAL_ONLY | — | `test_m18_*` |
| Webhook | Signed generic webhook (timestamp window, replay, uniform 401, queue) | COMPLETE | `webhooks.py` | — | yes | — | `test_webhooks` |
| CSV / JSON batch | validation, quarantine, dedup | COMPLETE | `batch_connectors` | — | yes | — | `test_acquisition_pipeline` |
| OEM API | credentialed pull polling, SSRF guard, cursor, schedule | COMPLETE | `oem_poller`, `acquisition.poll` job | Real OEM API | EXTERNAL_ONLY | — | `test_oem_polling` |
| Queue | durable jobs, SKIP LOCKED claim, retry/backoff, dead-letter, stale reclaim, idempotency, correlation id, graceful stop, failure-evidence hook | COMPLETE | `job_service`, `worker.py`, migration 0066 | Shared broker for very high scale (design in runbook) | yes | — | `test_background_jobs` (parallel claim) |
| Scheduler | idempotent recurring jobs (retention, dunning, OEM polls) | COMPLETE | `scheduler.py` | — | yes | — | `test_retention`, `test_oem_polling`, `test_billing_lifecycle` |
| Rate limiting | auth + policy middleware (ingest, webhook, LISA, analytics, admin, default), tenant/user/IP keyed, configurable, metrics; pluggable in-memory/Redis backend; fail-closed for sensitive policies, local fallback otherwise | COMPLETE | `rate_limit*.py` | Shared Redis deployed across instances | infra = EXTERNAL_ONLY | — | `test_rate_limit_policies`, `test_rate_limiter_backends` |
| Retention | policies, dry-run, floors, evidence kept, archive-before-delete, audited, scheduled, default OFF | COMPLETE | `retention_service`, 0067 | — | yes | — | `test_retention` |
| Performance | profiled; batch-strided HUMS, caches, one audit row per batch | COMPLETE | `PERFORMANCE_BENCHMARK.md` | Multi-worker scaling on prod hardware | EXTERNAL_ONLY | — | profile harness, `test_acquisition_pipeline` |

## Intelligence and operations

| Area | Capability | Status | Evidence | Missing work | Software? | Priority | Tests |
|---|---|---|---|---|---|---|---|
| Telemetry | validation, NaN/Inf rejection, timestamp gates, dedup, ordering, multi-vehicle, tenancy | COMPLETE | `telemetry_service` | — | yes | — | `test_telemetry_operations`, `test_m20_*` |
| HUMS | features, baselines, drift, exceedances, diagnostics, prognostics, evidence | COMPLETE (deterministic) | `services/hums/*` | Engineering-grade limits are operator data | — | — | `test_hums_*` |
| HUMS | per-sensor warning/critical limits, audited with previous values | COMPLETE | `set_sensor_thresholds`, 0070 | — | yes | — | `test_hums_thresholds` |
| HUMS | evaluation serialised per sensor (no duplicate exceedance/finding) | COMPLETE | advisory lock | — | yes | — | `test_concurrency` (mutation-checked) |
| M7 | one signal per exceedance; concurrent sync adopts winner | COMPLETE | `exceedance_signal_key`, SAVEPOINT insert | — | yes | — | `test_concurrency`, `test_customer_journey_*` |
| M7 | signal lifecycle audited | COMPLETE | `_audit_transition` | — | yes | — | `test_audit_coverage` |
| LISA | 60 tools; permission + feature (any-of) + suite (multi-suite aware) per call; fleet inventory filtered by entitlement | COMPLETE | `ai/tools.py` | Answer quality on real questions | quality = EXTERNAL_ONLY | — | `test_lisa_tool_matrix` (257), `test_lisa_security_entitlements` |
| MRO | work orders, tasks, inspections, findings, deferred, parts, procurement, AOG, TAT, release readiness | COMPLETE | services; live pages or redirects for all MRO routes, 10 non-MRO-critical pages are labelled not-connected | — | see G1-scope | — | existing suites |
| MRO/Compliance | audited mutations incl. obligation sync, inspection requirements, assessments, signals | COMPLETE | `test_audit_coverage`, AST scan | Unaudited remainder is health counters / LISA context / staging | — | — | `test_audit_coverage` |
| Knowledge graph | PostgreSQL is the only store; derived read-only digital twin rebuilt per read | COMPLETE (no Neo4j by design) | `digital_twin_service`, `knowledge_graph.py` | A separate graph database is **not** part of the product | — | — | `test_digital_twin`, `test_knowledge_graph` |

## Security, platform, observability

| Area | Capability | Status | Evidence | Tests |
|---|---|---|---|---|
| AuthN | DB is authority for user existence/activity/roles per request; exp+sub required; alg-none/tamper/expired/wrong-type rejected | COMPLETE | `deps.get_current_user`, `decode_token` | `test_security_hardening` |
| AuthZ | RBAC + tenant scoping + entitlement; facility/asset/component ownership checks | COMPLETE | services | `test_tenant_isolation_end_to_end`, `test_airframes`, `test_hums_thresholds` |
| Injection / XSS / CSRF / CORS / path traversal / SSRF | parameterised queries; JSON-only errors; bearer auth (no cookies); CORS allow-list; storage key sanitising; OEM SSRF guard | COMPLETE | — | `test_security_hardening`, `test_evidence_file_upload_api`, `test_oem_polling` |
| Logging | no passwords/tokens/secrets/raw telemetry in logs | COMPLETE | — | `test_logs_never_contain…` |
| Observability | metrics (HTTP, ingest, jobs, listeners, rate limit), readiness incl. schema head + job health, evidence-based source health | COMPLETE | `metrics.py`, `health.py` | `test_observability`, `test_health` |
| Database | migrations 0062–0070 up/down/up; drift guard; constraints (NULL-safe) | COMPLETE | `alembic/versions` | `test_schema_drift_guard`, thresholds constraint test |
| Frontend | strict sidebar = route guard = backend; live pages for evidence, parts, vendors, procurement, regulations, assessments, defects, notifications, maintenance program, components, engines, fleet pages; mock-only routes redirected or hidden | COMPLETE (G1 closed; see G1-scope) | `mock-only-routes.ts` | vitest 383, browser 44 + 56 + 42 + 25 |

## G1 — sample-data routes (closed for live sessions)

Of 34 sample-only routes, 24 redirect a live session to a connected page and 10 show a "Not connected to live data"
notice (listed under G1-scope above). Three more mixed pages (control tower, hangar, operations) redirect as well. Demo
mode keeps the sample pages. Verified by `tests/mock-only-routes.test.ts` and the browser leak scan (132 routes x 2
organizations, 0 markers).
