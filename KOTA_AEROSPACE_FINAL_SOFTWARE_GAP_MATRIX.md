# Kota Aerospace — Final Software Gap Matrix

Source of truth: the repository at branch `feature/post-freeze-productionization`, verified by tests (not by earlier
reports). Statuses: `COMPLETE`, `PARTIAL`, `MISSING`, `BROKEN`, `MOCKED`, `ASPIRATIONAL`, `EXTERNAL_ONLY`.
"Software?" = can the missing work be done and tested locally without hardware, credentials or production.

## Result

**Software-completable gaps remaining: not zero.** Two groups are open and are stated here rather than relabelled:

| # | Open item | Status | Why it is open |
|---|-----------|--------|----------------|
| G1 | 21 frontend routes still contain only bundled sample data (list below) | MOCKED | Each needs a page-level build against a backend that either does not exist (engines lifecycle beyond components, finance, reports, workspace, automation, integrations, pilot workflow, projects, discrepancies, material readiness, documents library, cart, pre-audit, org readiness) or is not yet wired. They are **hidden from live sessions** (notice card) and only render in Demo mode, so no customer sees fabricated data. |
| G2 | MAVLink TCP / serial server-side listeners | PARTIAL | UDP listener, HTTP push, MQTT, webhooks, OEM polling and the edge gateway daemon exist. A TCP listener is software-completable and low value; serial needs `pyserial` and a device. Serial radios are normally bridged to UDP (mavlink-router / gateway host). |

Everything else in scope is COMPLETE in software or `EXTERNAL_ONLY` (needs hardware, credentials or production).

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
| MAVLink | UDP listener (allow-list and/or signing required, back-pressure) | COMPLETE | `listeners/udp_mavlink.py` | — | yes | — | `test_listeners` (real sockets), `scripts/e2e_listener_smoke.py` (separate processes) |
| MAVLink | TCP / serial listeners | PARTIAL | — | see G2 | yes | low | — |
| MAVLink | Physical link behaviour, RF, real autopilot | EXTERNAL_ONLY | bench harness + plan | hardware | no | — | `scripts/mavlink_bench_harness.py` |
| MQTT | subscribe, filter, reconnect+backoff, TLS/plaintext policy, secret password | COMPLETE | `listeners/mqtt.py`, in-memory broker (test double) | Real broker validation | broker = EXTERNAL_ONLY | — | `test_listeners` |
| DJI | HMAC-signed webhook, fail closed | COMPLETE | `telemetry.py` | Real FlightHub | EXTERNAL_ONLY | — | `test_m18_*` |
| Webhook | Signed generic webhook (timestamp window, replay, uniform 401, queue) | COMPLETE | `webhooks.py` | — | yes | — | `test_webhooks` |
| CSV / JSON batch | validation, quarantine, dedup | COMPLETE | `batch_connectors` | — | yes | — | `test_acquisition_pipeline` |
| OEM API | credentialed pull polling, SSRF guard, cursor, schedule | COMPLETE | `oem_poller`, `acquisition.poll` job | Real OEM API | EXTERNAL_ONLY | — | `test_oem_polling` |
| Queue | durable jobs, SKIP LOCKED claim, retry/backoff, dead-letter, stale reclaim, idempotency, correlation id, graceful stop, failure-evidence hook | COMPLETE | `job_service`, `worker.py`, migration 0066 | Shared broker for very high scale (design in runbook) | yes | — | `test_background_jobs` (parallel claim) |
| Scheduler | idempotent recurring jobs (retention, dunning, OEM polls) | COMPLETE | `scheduler.py` | — | yes | — | `test_retention`, `test_oem_polling`, `test_billing_lifecycle` |
| Rate limiting | auth + policy middleware (ingest, webhook, LISA, analytics, admin, default), tenant/user/IP keyed, configurable, metrics, fail-open on internal error | COMPLETE (process-local) | `rate_limit*.py` | Shared limiter across instances | infra = EXTERNAL_ONLY | — | `test_rate_limit_policies` |
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
| MRO | work orders, tasks, inspections, findings, deferred, parts, procurement, AOG, TAT, release readiness | COMPLETE (backend) | services | Frontend for 21 sample-data modules | see G1 | medium | existing suites |
| MRO/Compliance | audited mutations incl. obligation sync, inspection requirements, assessments, signals | COMPLETE | `test_audit_coverage`, AST scan | Unaudited remainder is health counters / LISA context / staging | — | — | `test_audit_coverage` |
| Knowledge graph | PostgreSQL is the only store; derived read-only digital twin rebuilt per read | COMPLETE (no Neo4j by design) | `digital_twin_service` | A separate graph database is **not** part of the product | — | — | `test_digital_twin` |

## Security, platform, observability

| Area | Capability | Status | Evidence | Tests |
|---|---|---|---|---|
| AuthN | DB is authority for user existence/activity/roles per request; exp+sub required; alg-none/tamper/expired/wrong-type rejected | COMPLETE | `deps.get_current_user`, `decode_token` | `test_security_hardening` |
| AuthZ | RBAC + tenant scoping + entitlement; facility/asset/component ownership checks | COMPLETE | services | `test_tenant_isolation_end_to_end`, `test_airframes`, `test_hums_thresholds` |
| Injection / XSS / CSRF / CORS / path traversal / SSRF | parameterised queries; JSON-only errors; bearer auth (no cookies); CORS allow-list; storage key sanitising; OEM SSRF guard | COMPLETE | — | `test_security_hardening`, `test_evidence_file_upload_api`, `test_oem_polling` |
| Logging | no passwords/tokens/secrets/raw telemetry in logs | COMPLETE | — | `test_logs_never_contain…` |
| Observability | metrics (HTTP, ingest, jobs, listeners, rate limit), readiness incl. schema head + job health, evidence-based source health | COMPLETE | `metrics.py`, `health.py` | `test_observability`, `test_health` |
| Database | migrations 0062–0070 up/down/up; drift guard; constraints (NULL-safe) | COMPLETE | `alembic/versions` | `test_schema_drift_guard`, thresholds constraint test |
| Frontend | strict sidebar = route guard = backend; live pages for evidence, parts, vendors, procurement, regulations, assessments, defects, notifications, maintenance program, components, engines, fleet pages; mock-only routes redirected or hidden | COMPLETE except G1 | `mock-only-routes.ts` | vitest 369, browser 44 + 53 |

## G1 — routes still sample-data only (hidden from live sessions)

`/aircraft/[id]/configuration`, `/assessments/[id]/review`, `/automation`, `/compliance/pre-audit`, `/documents`,
`/finance`, `/finance/[id]`, `/fleet/aircraft/[id]/health`, `/integrations`, `/maintenance/discrepancies`,
`/maintenance/material-readiness`, `/maintenance/planning/[id]`, `/maintenance/projects`,
`/maintenance/projects/[id]`, `/maintenance/projects/[id]/intelligence`, `/organization/readiness`, `/pilot`,
`/procurement/cart`, `/reports`, `/reports/[id]`, `/workspace`.

Thirteen further sample-data routes redirect live sessions to a connected page (audit, executive, fleet health,
maintenance records/tasks/planning/release-readiness, organization usage, organization roles ×2, organization user
detail, platform features, evidence detail).
Product decision needed for G1: build each against real APIs, or retire it from the product.
