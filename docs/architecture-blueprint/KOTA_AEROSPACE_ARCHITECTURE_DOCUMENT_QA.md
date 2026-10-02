# Kota Aerospace Architecture Document — QA Report

Blueprint v1.0 · generated 2026-10-01 · evidence base `feature/post-freeze-productionization` @ `6bd38ce` (commit date 2026-10-01).

## 1. Repository sources inspected

- Backend: `backend/app` — 346 Python files, 57 routers (523 handlers, 252 mutating), 95 SQLAlchemy models, services, listeners, worker, scheduler, AI/LISA modules.
- Database: `backend/alembic/versions` — 70 migrations (0001 → 0070).
- Tests: `backend/tests` — 214 files; `frontend/tests` (vitest).
- Frontend: `frontend/` — Next.js 16.3.5, 137 pages, entitlement guard, mock-only route redirects.
- Runtime / CI: `backend/Dockerfile`, `infra/docker-compose.yml`, `.github/workflows/ci.yml`, `.vercel/project.json`.
- Documents: `docs/adr` (10 ADRs), `docs/ontology`, `docs/*.md`, root-level architecture and milestone reports (gap matrix, release readiness, data acquisition, security, entitlement, suite, LISA, observability, M17 intelligence, M14/H8 reports, domain events).
- Working tree had uncommitted line-ending changes on ~390 files; the audit used the committed HEAD (6bd38ce) via a git bundle.

Not inspected: hosted staging/production environments, provider consoles, production data, physical devices.

## 2. Independent verification runs

- Backend: `pytest` on Python 3.12.3 + PostgreSQL 16 → **2689 passed, 1 failed, 16 deselected** in 651 s.
  - Failed: `tests/integration/test_listeners.py::test_supervisor_starts_a_tcp_listener` — ConnectionRefused: the test connects before the supervisor's TCP server task has bound the port (no readiness wait); failed 3/3 re-runs in this environment, reported passing on the developer machine.
  - tests/integration/test_observability.py fails collection on Python 3.11 (3.12-only f-string syntax) — CI pins 3.11.
- Migrations: alembic upgrade head on an empty PostgreSQL 16 database: 0001 → 0070, clean.
- Frontend: vitest 37 files / 383 tests passed; tsc --noEmit clean (exit 0); ESLint 0 errors, 129 warnings.
- Not run: browser harness (needs a running stack and seed), `next build`, real-storage tests, any hardware or provider test.

## 3. Claims verified

- ✅ Modular monolith: one FastAPI app, three processes (API, worker/scheduler, listeners).
- ✅ PostgreSQL is the only store of record; job queue uses FOR UPDATE SKIP LOCKED; audit_events immutable by trigger (migration 0002).
- ✅ No Neo4j driver dependency; knowledge graph and digital twin are derived in PostgreSQL.
- ✅ Acquisition connectors (MAVLink v1/v2 with CRC_EXTRA, sequence, signing; MQTT; CSV/JSON; DJI and generic HMAC webhooks; OEM polling) converge on telemetry_service.process_normalized_event.
- ✅ HUMS engines (features, baselines, diagnostics, degradation, prognostics) and per-sensor limits (0070).
- ✅ M7 signals persisted in proactive_signal_records with audited lifecycle transitions.
- ✅ LISA: 61 tools; each declares required_permission and required_feature; deterministic airworthiness guard; one write-capable tool (run_assessment).
- ✅ Entitlements: suite → plan → subscription → overrides → limits, resolved per request; used by REST (require_feature) and LISA (_require_entitlement).
- ✅ Applicability: Kleene three-valued evaluation with configuration_snapshot and reasoning_trace.
- ✅ Work-order state machine (DRAFT … CLOSED, ON_HOLD, CANCELLED) with audited transitions.
- ✅ Evidence files with SHA-256 checksums in S3-compatible storage.

## 4. Claims not verified (or contradicted)

- ⚠️ Neo4j as derived graph (ADR-003, M14 report) — contradicted by code (F1).
- ⚠️ Transactional outbox (ADR-003 text) — no outbox table; jobs-in-transaction is the equivalent (F2).
- ⚠️ `ai_tool_audit_log` (LISA_ARCHITECTURE narrative) — not found; tool calls are not persisted (F5).
- ⚠️ Separate AI database role (ADR-004/005) — not found (F5).
- ⚠️ ADR-005 human_decision / final_status / previous_assessment_id lineage — not in schema (F8).
- ⚠️ Import-linter enforcement of module boundaries (ADR-001) — not configured.
- ⚠️ Redis cluster, TimescaleDB, Cloudflare WAF topology (deployment guide) — target only, flagged by the repo itself.
- ⚠️ RPO < 15 min, RTO < 1 h, WORM evidence (backup runbook) — no evidence of drill or bucket policy.
- ⚠️ Staging deployments on Vercel / Render / Neon — reported in documents, not inspected.
- ⚠️ Historical '2690 passed, 0 failed' — re-run gave 2689 passed, 1 failed (test start-up race) on Python 3.12; CI's Python 3.11 cannot collect one test file.
- ⚠️ FINAL_RELEASE_READINESS lists G1 as OPEN (21 routes) while the gap matrix lists it CLOSED (34 routes) — documents disagree.

## 5. New defects found during the audit

- **M7 work-order status filter** (`proactive_intelligence_service.py:74`) uses `AWAITING_PARTS` and `SCHEDULED`, which are not `WorkOrderStatus` values; overdue work orders in PLANNED, ASSIGNED, ON_HOLD or INSPECTION never raise overdue-maintenance signals (F7).
- **Async ingestion bypasses entitlement and organisation-suspension checks** — `acquisition_service._load_source` and job handlers check only DataSource status (F3).
- **Edge gateway buffer** is an in-memory `deque(maxlen=…)` and the uplink default token is a placeholder string `kota_edge_bearer_token` (F4).
- **Test reliability:** `test_supervisor_starts_a_tcp_listener` connects before the listener binds (F9).

No application code, schema, migration, deployment or configuration was changed.

## 6. Diagrams completed

- D01 master ecosystem (radial)
- D02 layered architecture
- D03 backend modular monolith
- D04 infrastructure topology (dark)
- D05 drone-to-cloud connectivity
- D06 HUMS processing
- D07 intelligence ownership + signal lifecycle
- D08 LISA & agentic AI
- D09 compliance & evidence
- D10 MRO & asset lifecycle
- D11 suite/plan/entitlement
- D12 security & trust boundaries
- D13 deployment & operations
- D14·1–3 end-to-end scenarios (sequence)
- X01 event architecture
- X02 traceability lineage
- X03 roadmap
- X04 connectivity decision tree
- Dependency matrix (HTML heat table)
- Status register (44 capabilities)

## 7. Diagrams requiring validation

- D04 / D13 hosting (Vercel, Render, Neon) — confirm against provider consoles.
- D05 physical paths (companion computer, GCS relay, satellite) — confirm on a bench with a real autopilot.
- D10 dependency matrix — derived from service imports and reading; confirm with an import graph tool before enforcing.
- D12 encryption at rest / backups — confirm provider settings.
- ADR-008 engine-as-subject — confirm whether engine-subject evaluations exist.

## 8. Broken or unclear dependencies

- M06 → M03 entitlement check missing on async paths.
- M08 reads WorkOrder statuses through string literals instead of model constants.
- Two proactive surfaces (/proactive and /intelligence/signals).
- M7 and HUMS write during GET requests (sync-on-read).
- 'M14' names both a milestone and a service.

## 9. Visual and PDF rendering checks

- PDF rendered with Chromium (Playwright), A4 landscape, 42 pages, fonts embedded (IBM Plex Sans / Condensed / Mono, Space Grotesk; DejaVu Sans fallback for arrows).
- Every page rendered to PNG (pypdfium2) and inspected visually; overflow check on every page: no page overflows (automated scrollHeight check).
- Fixed during QA: clipped zone labels, connectors crossing boxes (D02, D05, D06, D07, D10, X01), misleading one-to-one arrows (D05 buses), badge/title collisions, empty card stretch, roadmap header remnants, sequence labels clipped at the right edge, overflowing tables split or compacted.
- Vector diagrams are inline SVG (crisp at any zoom). Clickable contents and cross-references are internal PDF links; PDF outline/tagging requested from Chromium.
- 20 standalone SVG sources exported.

## 10. Known limitations

- Reference images mentioned in the brief were not supplied; visual direction followed the written description.
- Smallest diagram labels print at ≈6.5 pt on A4; use the SVG sources for large-format printing.
- Some scenario message labels sit close to step numbers on dense rows.
- Not a substitute for a penetration test, capacity test or provider validation.

## 11. Recommended follow-up actions

- Fix the M7 status filter (one-line change + regression test) — highest value, lowest effort.
- Approve or reject ADR-011 (PostgreSQL derived graph) and remove Neo4j from docker-compose.
- Add the entitlement re-check to acquisition paths (ADR-013).
- Pin Python 3.12 in CI and Dockerfile; add vitest to CI; add a readiness wait to the listener test.
- Decide the first supported field connectivity path and run the bench test.
- Assign an owner for this blueprint; regenerate it after each milestone.
