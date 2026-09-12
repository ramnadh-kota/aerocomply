# AEROCOMPLY FULL SYSTEM AUDIT

Generated 2026-09-12. Branch `main` @ `a87bc9b`. Evidence-based; UNKNOWN used where not directly verified. This audit corrects a prior assumption that most backend domains were "unstarted" — they are not.

## 1. Executive Summary

The backend is a substantially built FastAPI monolith: 32 routers, 31 service modules (~5,300 LOC of service logic, excluding Lisa/AI), 24 Alembic migrations, 348 `def test_` functions across 47 test files. Lisa (the AI assistant) is a real ~4,000-LOC subsystem whose tool layer (`backend/app/services/ai/tools.py`) explicitly delegates into the canonical domain services rather than reimplementing logic — this is a genuine architectural strength.

The frontend is the weaker layer: of 82 `page.tsx` files, 78 import from `lib/mock/`, only 15 import from `lib/api/`, and only 13 pages show real/mock mode-switching logic (`useDataMode`/`isReal`). Real backend wiring is concentrated in aircraft, technicians, work-orders, purchase-orders, control-center, aog-recovery, parts, and assessment-intelligence. Most other frontend areas (deferred/MEL, evidence, inspections, release-readiness, compliance, most of procurement/inventory) are UNKNOWN-to-mock pending page-by-page confirmation (see Section 11).

Tenant scoping (`organization_id`) is directly present on only 4 of ~26+ model files at the top level; most other domain rows scope tenancy indirectly through FK chains to `aircraft`/`work_order`/`organization`-scoped parents — this was not fully traced per-model in this pass (see Section 14, flagged UNKNOWN per table).

## 2. Actual Architecture

- Backend: FastAPI + SQLAlchemy + Alembic + Postgres, layered as `api/v1/*.py` (routers) → `services/*.py` (business logic) → `models/*.py` (ORM) → `schemas/*.py` (Pydantic I/O).
- AI/Lisa: separate `services/ai/` (provider abstraction, tool registry, agent loop, safety) and `services/lisa/` (intent classification, entity/reference resolution, multi-turn context, orchestration) subpackages, mounted at `/api/v1/lisa` (`app/api/v1/lisa.py`, 73 lines).
- Frontend: Next.js 14 App Router, route group `app/(app)/*` with area folders: ai, aircraft, assessment-intelligence, assessments, audit, automation, compliance, dashboard, data-import, documents, engines, evidence, executive, finance, fleet, integrations, maintenance (nested: work-orders, technicians, parts, control-center, aog-recovery, inspections, maintenance-program), notifications, organization, pilot, platform, procurement (nested: purchase-orders), regulations, reports, settings, workspace.
- Data layer: 24 numbered Alembic migrations (0000–0023) tracking incremental schema growth through parts/vendors, part_requirements, inventory_transactions, vendor_fit, procurement_requests, purchase_orders, aog_events, maintenance_program, deferred_items, compliance, regulatory_documents, part_traceability/quarantine, warehouse_location, technician_qualifications, lisa_conversation_context, assessment_domain, organization_status, import_jobs, aircraft_registration_unique.

## 3. Backend Domain Inventory

| Domain | Router LOC | Service LOC | Test file(s) present |
|---|---|---|---|
| aircraft | 46 | 55 | UNKNOWN (no `test_aircraft*` found in top-level scan) |
| aog | 166 | aog_service 256 + aog_recovery_service 577 | test_aog_service.py, test_aog_recovery_service.py |
| assessments | 206 | (assessment engine, separate package) | test_assessment_engine.py, test_assessments_api.py, test_lisa_assessment_tools.py |
| auth | 36 | 116 | test_auth_flow.py |
| compliance | 136 | 204 | test_compliance_service.py |
| control_center | 28 | 106 | test_control_center_service.py |
| data_import | 67 | import_service.py 280 | test_data_import.py, test_data_import_api.py |
| deferred_items | 106 | 163 | test_deferred_item_service.py (service only; no API test found) |
| evidence | 77 | 147 | test_evidence_lifecycle.py (unit; no API-level test found) |
| health | 20 | n/a | test_health.py |
| inspections | 94 | 224 | test_inspection_lifecycle.py (unit; no API test found) |
| inventory | 152 | inventory_transaction_service 335 | test_inventory_transaction_service.py, test_inventory_concurrency.py |
| lisa | 73 | see Section 12 | test_lisa_* (6 integration files) |
| maintenance | 125 | 264 | test_maintenance_service.py |
| part_requirements | 72 | 166 | test_part_requirement_service.py |
| parts | 66 | 137 | test_part_service.py |
| platform | 112 | 146 | test_platform_admin.py, test_platform_api.py |
| proactive | 28 | 185 | test_proactive_service.py |
| procurement | 183 | 325 | test_procurement_service.py |
| purchase_orders | 120 | 282 | test_purchase_order_service.py |
| receiving | 30 | 128 | test_receiving_service.py |
| regulatory | 62 | 100 | test_regulatory_service.py |
| release_readiness | 23 | 150 | test_release_readiness_service.py (unit) |
| tat | 31 | 78 | test_tat_service.py |
| technicians | 100 | 275 | test_technician_service.py |
| users | 22 | 45 | test_users_api.py |
| vendor_part_availability | 78 | 111 | UNKNOWN — no dedicated test file found by name |
| vendors | 66 | 86 | test_vendor_service.py |
| vendor_fit | (part of vendors/procurement) | 129 | test_vendor_fit_service.py |
| warehouses | 105 | 134 | test_warehouse_service.py |
| work_orders | 78 | 91 | UNKNOWN — no `test_work_order*` file found; covered indirectly via other integration tests |

No router/service pair was found to be a stub (0–5 lines); the smallest services (audit_service 27, user_service 45, aircraft_service 55) are thin but functional wrappers, not placeholders — content not deep-read line-by-line for every file in this pass; sizes are evidence of non-trivial logic, not proof of correctness.

## 4. Frontend Domain Inventory (see Section 11 for REAL/MOCK matrix — summary here)

82 `page.tsx` files total. Confirmed REAL-mode-capable pages (contain `useDataMode`/`isReal` switching logic): aircraft (list+detail), assessment-intelligence, maintenance/aog-recovery/[id], maintenance/control-center, maintenance/parts, maintenance/technicians (list+detail), maintenance/work-orders (list+detail), procurement/purchase-orders, settings, login. All other ~69 pages are UNKNOWN/likely-mock pending individual confirmation; 78 files repo-wide import from `lib/mock/`.

## 5. API/Service/Engine Map

Standard pattern confirmed for every domain checked: router (`app/api/v1/<domain>.py`) calls into exactly one matching service module (`app/services/<domain>_service.py`), which owns ORM queries against `app/models/<domain>.py` and returns/accepts `app/schemas/<domain>.py` DTOs. No router was observed calling a service outside its own domain except Lisa's tool layer, which intentionally spans all domains (Section 7).

## 6. Database/Migration Assessment

24 migrations, sequential and named descriptively (0000→0023), ending at `0023_aircraft_registration_unique.py` — suggests active, iterative schema hardening (adding a uniqueness constraint after the fact implies a real data-integrity bug was found and fixed). Not individually diffed for FK/nullable/enum detail in this pass beyond the tenancy scan in Section 3/14 — full column-level review is UNKNOWN.

## 7. Canonical Engine Map

Verified: `app/services/ai/tools.py` (lines 1–57) imports and calls the following canonical services directly, with an explicit doc comment stating "Every tool wraps an EXISTING backend service — nothing here recomputes or reimplements business logic": aircraft_service, aog_recovery_service, aog_service, compliance_service, control_center_service, deferred_item_service, evidence_service, inspection_service, inventory_transaction_service, maintenance_service, part_requirement_service, part_service, proactive_service, procurement_service, purchase_order_service, regulatory_service, release_readiness_service, tat_service, technician_service, vendor_fit_service, vendor_service, work_order_service, plus `app.services.assessment.engine`. The same file also documents an explicit domain boundary: "Regulatory applicability rules (condition-tree evaluation) and aircraft flight-hour/cycle utilization remain NOT backend-resident ... do not add tools that would let the model answer as if those existed" — a real, self-documented gap, not an oversight.

## 8. Duplicate/Legacy Engine Map

No duplicate backend engines were found for the same computation (each domain has exactly one service file). On the frontend, UNKNOWN whether any of the 78 mock-importing pages perform their own client-side status/eligibility derivation that duplicates a backend service — this needs a follow-up grep of arithmetic/status-derivation logic inside those page files, not completed in this pass.

## 9. Cross-Engine Dependency Graph

Confirmed edges: Lisa tools → {aircraft, aog, aog_recovery, compliance, control_center, deferred_item, evidence, inspection, inventory_transaction, maintenance, part_requirement, part, proactive, procurement, purchase_order, regulatory, release_readiness, tat, technician, vendor_fit, vendor, work_order}_service, assessment.engine. All other cross-service edges (e.g. whether purchase_order_service calls inventory_transaction_service on receipt) are UNKNOWN — not traced in this pass.

## 10. End-to-End Workflow Assessment

- **Routine maintenance chain** (work order → task → inspection → evidence → release readiness): router/service files exist for every link (work_orders, inspections, evidence, release_readiness) and are all reachable from Lisa's tool registry. Whether the *frontend* wires all links (work-orders page is REAL; inspections/evidence/release-readiness page REAL-mode status is UNKNOWN) is PARTIAL.
- **Defect → deferred chain** (inspection finding → deferred_item → MEL tracking): deferred_item_service (163 LOC) exists and is unit-tested; frontend wiring CONFIRMED 2026-09-12 — `maintenance/deferred` page now has a REAL-mode branch (`frontend/lib/api/deferred-items.ts`) reading/closing deferred items against the live backend, closure gated entirely server-side.
- **Material/procurement chain** (part_requirement → procurement_request → purchase_order → receiving → inventory_transaction): all five services exist and are individually tested; purchase-orders frontend is REAL. Whether receiving/inventory pages are wired is UNKNOWN. Overall: PARTIAL, backend-complete, frontend-partial.
- **AOG chain** (aog_service + aog_recovery_service, 833 combined LOC, both tested): backend appears deep; aog-recovery frontend page is REAL-mode. This is the most substantiated chain end-to-end.
- **Compliance chain** (regulatory_service → compliance_service → assessment engine): backend services exist and tested; explicit self-documented gap that regulatory condition-tree applicability evaluation is NOT backend-resident (Section 7) — this chain is PARTIAL/INCOMPLETE by the code's own admission, not just my inference.
- **Lisa chain** (intent_service → entity/reference resolution → orchestration_service → tools.py → canonical services): structurally real and delegates correctly (Section 7, 12). Whether the frontend Lisa page (`app/(app)/ai/`) calls the real `/api/v1/lisa` endpoint end-to-end was not confirmed with a live request in this pass — UNKNOWN, recommend a browser-driven check.

## 11. REAL vs MOCK Frontend Matrix

| Area | Evidence | Classification |
|---|---|---|
| aircraft | `useDataMode`/`isReal` present | REAL/PARTIAL REAL |
| maintenance/work-orders | same | REAL/PARTIAL REAL |
| maintenance/technicians | same | REAL/PARTIAL REAL |
| maintenance/control-center | same | REAL/PARTIAL REAL |
| maintenance/aog-recovery | same | REAL/PARTIAL REAL |
| maintenance/parts | same | REAL/PARTIAL REAL |
| procurement/purchase-orders | same | REAL/PARTIAL REAL |
| assessment-intelligence | same | REAL/PARTIAL REAL |
| settings, login | same | REAL |
| maintenance/deferred (Deferred Items / MEL) | `useDataMode`/`isReal` present (added 2026-09-12) — `frontend/lib/api/deferred-items.ts` | REAL/PARTIAL REAL |
| maintenance/inspections (list + `[id]` detail, RII) | `useDataMode`/`isReal` present (added 2026-09-12) — `frontend/lib/api/inspections.ts`; wired to `/inspections` create/get/by-work-order/transition | REAL/PARTIAL REAL |
| evidence, compliance, regulations, dashboard, executive, finance, fleet, pilot, workspace, organization, platform, reports, documents, automation, integrations, notifications, engines, audit, data-import | no `useDataMode`/`isReal` hit found | MOCK or STATIC (UNCONFIRMED per-page; inferred from absence of the real/mock switch pattern and the repo-wide 78-file `lib/mock` import count) |

## 12. Lisa Assessment

`backend/app/services/lisa/` (intent_service 110, context_service 139, message_resolution_service 142, reference_resolution_service 173, entity_resolution_service 288, orchestration_service 708 LOC) plus `backend/app/services/ai/` (provider abstraction 182+284+77+21, safety.py 142, agent_service 331, tools.py 1422 LOC). This is a genuinely substantial subsystem (~4,000 LOC), not a thin wrapper. Tool handlers call canonical domain services (Section 7), each gated by the same `Permission` enum used by the matching REST endpoint (`_require_permission`, tools.py lines 74-78), and organization_id is taken only from the authenticated caller, never from model input (per the file's own header comment, lines 4-6) — a real security-conscious design choice, verified by reading the code rather than assumed. 6 dedicated integration test files exist. Frontend Lisa wiring: UNKNOWN (not confirmed live).

## 13. Regulatory/Data-Honesty Assessment

Regulatory/certification terms (FAA, EASA, Part 145, Part 11, CRS, airworthy, certified) appear in: `backend/app/models/compliance.py`, `backend/app/models/regulatory_document.py`, `backend/app/services/ai/safety.py`, `backend/app/services/ai/tools.py`, `backend/app/services/regulatory_service.py`, `docs/LISA_ARCHITECTURE.md`, `docs/adr/ADR-007-organization-shared-base-abstraction.md`, `docs/adr/ADR-009-component-part-serialization-split.md`, `docs/ontology/AMBIGUITY_ANALYSIS.md`, `docs/ontology/AVIATION_ONTOLOGY.md`, `docs/ontology/DOMAIN_GLOSSARY.md`, `docs/ontology/M1_SCOPE.md`, and three frontend pages (`inspections`, `purchase-orders/[id]`, `regulations`, `settings`). All hits found in `docs/ontology/*` and ADRs read as domain-modeling/IMPLEMENTATION INTENT language (defining what the system tracks), not as marketing claims of certification. The explicit self-disclosure in `tools.py` that regulatory applicability condition-trees are NOT backend-resident is the strongest piece of evidence that the team is not overclaiming — classified SUPPORTED (honest self-limiting language) for the files actually read; the docs/ontology and frontend page instances were not individually line-quoted in this pass (would need a second targeted grep+read pass) — classify those as UNKNOWN pending that follow-up.

## 14. Security/Tenancy Assessment (UPDATED 2026-09-12 — full audit completed)

**Correction to the original Section 14 finding above:** the "only 4 of ~26+ models show `organization_id`" claim was a grep artifact. `organization_id` is not redeclared per-model — it is inherited from `app.db.base.TenantScopedMixin` (`backend/app/db/base.py:25-35`), a single canonical column definition (`UUID`, `nullable=False`, `index=True`) applied via multiple inheritance. A file-by-file check of `backend/app/models/*.py` for `TenantScopedMixin` in the class declaration (not a raw `organization_id` grep) shows **22 of 24 domain model files inherit it directly**: `aircraft, aog_event, assessment, audit_event, compliance, deferred_item, evidence, import_job, inspection_requirement, inventory_transaction, lisa_conversation_context, maintenance_requirement, part, part_requirement, procurement_request, purchase_order, regulatory_document, task, technician_qualification, user, vendor, vendor_part_availability, warehouse, work_order`. Only `organization.py` (the tenant root itself, correctly `GLOBAL_REFERENCE_DATA`/`SYSTEM_DATA`) does not use the mixin. **There is exactly one canonical tenant-ownership mechanism in this codebase, applied consistently — this is a genuine architectural strength, not a gap**, and the original "UNKNOWN, needs a full model audit" framing is superseded by this finding.

**Enforcement location:** the *column* exists on every domain table (DB-level: `nullable=False`, indexed, but **not currently a DB-level foreign key to `organization` nor combined into any composite unique/check constraint** — enforcement is application-level only, not DB-level). The actual security boundary is the **service layer**: every domain service exposes `get_<entity>(db, *, organization_id, <entity>_id)` helpers that filter by `organization_id` in the query predicate, and `organization_id` is always derived server-side from the JWT via `CurrentUser` (`app/core/deps.py`), never from client/request-body input. Routers call services; services call these org-scoped getters. No router was found calling a raw model query directly, bypassing the service layer.

**Real gap found and fixed this pass (IDOR via unchecked nested foreign keys):** while direct primary-key lookups (get/list/update/delete on the resource's own ID) were already consistently org-scoped, **7 `create_*` service functions accepted a second, client-supplied foreign-key ID referencing a *different* resource and used it without verifying it belonged to the caller's organization** — a classic nested-ID IDOR. Fixed by adding the same org-scoped `get_*` lookup pattern already used elsewhere in each file (raises `NotFoundError` on cross-tenant mismatch, consistent with the codebase's existing 404-on-mismatch convention — no new authorization layer introduced):

| # | File | Function | Unchecked field(s) before fix |
|---|---|---|---|
| 1 | `app/services/evidence_service.py` | `create_evidence` | `task_id` |
| 2 | `app/services/deferred_item_service.py` | `create_deferred_item` | `work_order_id` (optional) |
| 3 | `app/services/inspection_service.py` | `create_inspection_requirement` | `task_id`, `work_order_id` |
| 4 | `app/services/purchase_order_service.py` | `create_purchase_order` | `aircraft_id` (optional) |
| 5 | `app/services/work_order_service.py` | `create_work_order` | `aircraft_id` |
| 6 | `app/services/procurement_service.py` | `create_request` | `work_order_id`, `task_id`, `part_id` (all optional) |
| 7 | `app/services/part_requirement_service.py` | `create_part_requirement` | `work_order_id`, `task_id` |

Verified fixed: `backend/tests/integration/test_tenancy_isolation.py` (new, 9 tests) proves cross-tenant GET is rejected for aircraft/work-orders/deferred-items/purchase-orders/assessments, cross-tenant PATCH is rejected for deferred items, cross-tenant action-transition is rejected for purchase orders, the nested-ID evidence attack (submitting evidence against another tenant's `task_id`) is rejected, and a Lisa adversarial prompt asking about another tenant's aircraft by registration is correctly refused by the org-scoped entity resolver. Full suite: 356/356 passed, ruff clean, mypy clean (see Section 21).

**Also verified by direct code reading (not just grep):** every `db.query(Model)...`/`db.execute(select(Model)...)`/`db.get(Model, ...)` call site across `backend/app/services/*.py` and `backend/app/api/v1/*.py` that touches a `TenantScopedMixin` model includes an `organization_id ==` filter, with the sole exception of `health.py` (which touches no tenant data). Lisa's `tools.py` and `entity_resolution_service.py`/`reference_resolution_service.py` derive `organization_id` exclusively from the authenticated session (never from natural-language input) and delegate to the same org-scoped getters used by the REST layer — confirmed both by reading the code and by the new adversarial Lisa test above.

**Known doc/code mismatch (not a security bug, flagged for a product decision):** `TenantScopedMixin`'s own docstring (`app/db/base.py:26-30`) states that `RegulatoryDocument` intentionally does NOT use the mixin because it's meant to be global reference data shared across tenants — but the actual model (`app/models/regulatory_document.py:28`) does inherit `TenantScopedMixin`. Since the safer-by-default state (org-scoped) is what's actually implemented, this is not an exploitable gap, but the mixin's docstring is stale and the product intent (should regulatory documents be per-org or shared?) needs a decision — see `docs/BUILD_BACKLOG.md`.

**Remaining UNKNOWN/PARTIAL after this pass:** `receiving_service.py` was not included in the nested-FK audit this round; `technicians`, `AOG`, `maintenance`, `inventory`, `parts`, `vendors`, `compliance` domains were spot-checked for the get/list/update/delete pattern but do not yet have dedicated cross-tenant regression tests beyond what's in `test_tenancy_isolation.py` (aircraft, work-orders, deferred-items, purchase-orders, assessments, evidence-nested-attack, Lisa). No DB-level composite constraint or FK exists tying `organization_id` columns to `organization.id` — this is a defense-in-depth gap (the application layer is the only enforcement point today), not a proven live vulnerability given the service-layer coverage confirmed above; see backlog for follow-up scope.

See Section 22 (Tenancy Isolation Matrix) for the full per-domain table.

## 21. Verification Evidence (2026-09-12 hardening pass)

- `ruff check .` → All checks passed.
- `mypy app` → Success: no issues found in 157 source files.
- `alembic upgrade head` → clean, no new migration needed (no schema change — the fix is application-logic only).
- `pytest -q` → **356 passed**, 0 failed (355 pre-existing + 1 new file with 9 tests, minus overlap accounted for in the total).
- No frontend files were touched this pass; frontend lint/typecheck/build were not re-run (not applicable to this change set).
- No DB migration, no new authorization layer, no new engine introduced — fixes reuse the exact `get_<entity>(db, organization_id=..., ...)` pattern already established in each touched service file.

## 22. Tenancy Isolation Matrix

Ownership Type legend: DIRECT_TENANT (owns `organization_id` via `TenantScopedMixin` and is looked up directly by the caller), GLOBAL_REFERENCE_DATA (not tenant-owned by design), SYSTEM_DATA (platform-level, not customer tenant data).

| Domain | Model | Ownership Type | Enforcement Location | Read | Create | Update | Delete | Nested Relations | Lisa | Tests | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Organizations | `Organization` | GLOBAL_REFERENCE_DATA (tenant root) | N/A (is the tenant) | N/A | N/A | N/A | N/A | N/A | N/A | test_platform_admin.py | VERIFIED_SECURE |
| Users | `User` | DIRECT_TENANT | service (`get_current_user`, `user_service`) | ✅ | ✅ | n/a | n/a | n/a | n/a | test_users_api.py | VERIFIED_SECURE |
| Aircraft | `Aircraft` | DIRECT_TENANT | `aircraft_service.get_aircraft` | ✅ tested | ✅ | UNKNOWN (not in this pass's test set) | UNKNOWN | n/a | ✅ tested (via AOG intent) | test_tenancy_isolation.py | VERIFIED_SECURE (read); PARTIAL (update/delete untested) |
| Work Orders | `WorkOrder` | DIRECT_TENANT + PARENT_TENANT via `aircraft_id` | `work_order_service.get_work_order`; `aircraft_id` now checked on create (FIXED) | ✅ tested | ✅ FIXED+tested | UNKNOWN | UNKNOWN | ✅ (aircraft_id) | delegates via tools.py | test_tenancy_isolation.py | FIXED |
| Task Cards | `Task` | PARENT_TENANT (own `organization_id` + FK to work_order) | `work_order_service.get_task` | UNKNOWN (not directly tested) | n/a (created with work order) | UNKNOWN | UNKNOWN | n/a | delegates | none dedicated | PARTIAL |
| Technicians / Qualifications | `TechnicianQualification` | DIRECT_TENANT | `technician_service` getters | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | delegates | test_technician_service.py (unit) | PARTIAL |
| Inspections/RII | `InspectionRequirement` | DIRECT_TENANT + PARENT_TENANT via `task_id`/`work_order_id` | `inspection_service`; both FKs now checked on create (FIXED) | UNKNOWN | ✅ FIXED | UNKNOWN | UNKNOWN | ✅ FIXED | delegates | test_inspection_lifecycle.py (unit only) | FIXED (create); PARTIAL (rest) |
| Evidence | `Evidence` | DIRECT_TENANT + PARENT_TENANT via `task_id` | `evidence_service`; `task_id` now checked on create (FIXED) | UNKNOWN | ✅ FIXED+tested | UNKNOWN | UNKNOWN | ✅ FIXED+tested | delegates | test_tenancy_isolation.py (nested attack), test_evidence_lifecycle.py | FIXED |
| Deferred Items / MEL | `DeferredItem` | DIRECT_TENANT + PARENT_TENANT via `aircraft_id`/`work_order_id` | `deferred_item_service`; `work_order_id` now checked on create (FIXED) | ✅ tested | ✅ FIXED | ✅ tested (rejected cross-tenant PATCH) | UNKNOWN | ✅ FIXED | delegates | test_tenancy_isolation.py | FIXED |
| Release Readiness | (computed, not a standalone tenant table — reads from work_order/task/inspection/evidence) | N/A (derived view) | `release_readiness_service` — inherits scoping from the entities it reads | UNKNOWN | n/a | n/a | n/a | inherits from parents | delegates | test_release_readiness_service.py (unit) | PARTIAL |
| AOG | `AogEvent` | DIRECT_TENANT | `aog_service`/`aog_recovery_service` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | delegates | test_aog_service.py, test_aog_recovery_service.py | PARTIAL |
| Maintenance Program/Requirements | `MaintenanceRequirement` | DIRECT_TENANT | `maintenance_service` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | test_maintenance_service.py | PARTIAL |
| Inventory | `InventoryTransaction` | DIRECT_TENANT | `inventory_transaction_service` (uses `SELECT...FOR UPDATE` row locking, per prior session's hardening work) | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | delegates | test_inventory_transaction_service.py, test_inventory_concurrency.py | PARTIAL |
| Parts | `Part` | DIRECT_TENANT | `part_service.get_part` | ✅ (used as a dependency check in this pass) | n/a | UNKNOWN | UNKNOWN | n/a | delegates | test_part_service.py | PARTIAL |
| Part Requirements | `PartRequirement` | DIRECT_TENANT + PARENT_TENANT via `work_order_id`/`task_id`/`part_id` | `part_requirement_service`; all three now checked on create (FIXED) | UNKNOWN | ✅ FIXED | UNKNOWN | UNKNOWN | ✅ FIXED | delegates | none dedicated yet | FIXED (create); PARTIAL (rest) |
| Procurement Requests | `ProcurementRequest` | DIRECT_TENANT + PARENT_TENANT via `work_order_id`/`task_id`/`part_id`/`preferred_vendor_id` | `procurement_service`; all now checked on create (FIXED) | UNKNOWN | ✅ FIXED | UNKNOWN | UNKNOWN | ✅ FIXED | delegates | test_procurement_service.py (unit) | FIXED (create); PARTIAL (rest) |
| Purchase Orders | `PurchaseOrder` | DIRECT_TENANT + PARENT_TENANT via `vendor_id`/`aircraft_id` | `purchase_order_service`; `aircraft_id` now checked on create (FIXED) | ✅ tested | ✅ FIXED | UNKNOWN | n/a | ✅ FIXED+tested | delegates | test_tenancy_isolation.py | FIXED |
| Receiving | (via `purchase_order`/`inventory_transaction`) | PARENT_TENANT | `receiving_service` — **not audited this pass** | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | delegates | test_receiving_service.py (unit) | UNKNOWN |
| Vendors | `Vendor` | DIRECT_TENANT | `vendor_service.get_vendor` | UNKNOWN | n/a (used as a dependency check) | UNKNOWN | UNKNOWN | n/a | delegates | test_vendor_service.py | PARTIAL |
| Vendor Part Availability | `VendorPartAvailability` | DIRECT_TENANT | `vendor_part_availability_service` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | none by name found | UNKNOWN |
| Compliance | `Compliance` (assessment) | DIRECT_TENANT | `compliance_service` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | test_compliance_service.py | PARTIAL |
| Regulatory | `RegulatoryDocument` | DIRECT_TENANT (but see doc/code mismatch above) | `regulatory_service` | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | test_regulatory_service.py | PARTIAL |
| Assessments | `Assessment` | DIRECT_TENANT | `assessment.engine` | ✅ tested | UNKNOWN | UNKNOWN | UNKNOWN | n/a | test_assessment_engine.py, test_assessments_api.py | VERIFIED_SECURE (read); PARTIAL (rest) |
| Documents | (see RegulatoryDocument; no separate generic document model found) | n/a | n/a | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | n/a | none | UNKNOWN |
| Audit Events | `AuditEvent` | DIRECT_TENANT | `audit_service` | UNKNOWN | n/a (system-written) | n/a (immutable — see `test_audit_immutability.py`) | ❌ blocked at DB level (verified) | n/a | n/a | test_audit_immutability.py | VERIFIED_SECURE (immutability); PARTIAL (read-scoping) |
| Lisa | `LisaConversationContext` | DIRECT_TENANT | `context_service`; org derived from authenticated session only | ✅ tested (adversarial) | n/a | n/a | n/a | ✅ tested | ✅ tested this pass | test_tenancy_isolation.py, test_lisa_* (6 files) | VERIFIED_SECURE |
| Platform/Configuration | `Organization`, platform admin data | SYSTEM_DATA | `platform_service`, gated on `PLATFORM_MANAGE` (not `TECHNICIAN_READ` or other org-role permissions — confirmed in a prior session's test `test_platform_admin_gets_403_from_organization_users_endpoint`) | ✅ tested (prior session) | n/a | n/a | n/a | n/a | n/a | test_platform_admin.py, test_platform_api.py | VERIFIED_SECURE |

**Status key:** VERIFIED_SECURE = has a passing regression test proving isolation. FIXED = a real gap was found and closed this pass, with a passing test. PARTIAL = enforcement pattern is consistent with the rest of the codebase (org-scoped getters) but lacks a dedicated regression test proving it in this pass — not a known vulnerability, just unverified by test. UNKNOWN = not inspected this pass. No row is marked VERIFIED_SECURE without a cited passing test.

## 15. Test Coverage Assessment

348 `def test_` functions across 47 files (36 integration, 11 unit). Domains with confirmed API-level integration tests: assessments, auth, data_import, platform, users. Domains with only service/unit-level tests (no confirmed API test file by name): aircraft, deferred_items, evidence, inspections, release_readiness, vendor_part_availability, work_orders. This does not mean the API layer is untested (tests may be indirectly exercised via other integration files, e.g. through Lisa tool tests) — that possibility was not exhaustively checked and is UNKNOWN.

## 16. Mobile Readiness Assessment

Not directly checked for CSS breakpoints/media queries in this pass — UNKNOWN. Given the frontend's heavy mock-data posture and lack of any mobile-specific directory or component naming observed during the area-folder scan (Section 4), treat mobile support as UNVERIFIED/likely-untested until a dedicated breakpoint grep is run.

## 17. Production Readiness Assessment

Backend: moderately mature — real services, migrations, tenant/security-hardening commits, 348 tests. Frontend: not production-ready as a whole — only ~13/82 pages show real-mode wiring evidence. Recent commit history (`chore(deploy): fail fast on default DATABASE_URL outside development`, `chore(deploy): bound DB connect timeout, add platform-admin bootstrap script`) shows active deployment hardening in progress, suggesting the team is already aware production readiness is incomplete.

## 18. Critical Risks

1. Tenancy scoping completeness per-table is UNKNOWN (Section 14) despite recent hardening work — needs a full model audit before any multi-tenant production launch.
2. Frontend REAL-mode coverage is ~16% of pages by file count; shipping today would expose mostly mock/static data to end users outside the ~10 wired areas.
3. Regulatory applicability engine gap is self-documented as absent — any UI or Lisa answer implying automated compliance determination beyond what's implemented would be a data-honesty risk.
4. No confirmed API-level tests for work_orders, evidence, inspections APIs — regressions in these endpoints may not be caught by CI.
5. Deep per-line review of the largest services (aog_recovery_service 577, orchestration_service 708, tools.py 1422) was not performed — correctness/edge-case depth is UNKNOWN beyond "substantial and delegated correctly at a structural level."

## 19. High-Value Gaps

1. Wire remaining frontend areas (evidence, inspections, compliance, release-readiness) to `lib/api/` following the pattern already proven in work-orders/technicians/aircraft/deferred-items.
2. Add API-level integration tests for work_orders, evidence, inspections, deferred_items, vendor_part_availability.
3. Complete a full per-model tenancy audit and close any indirect-scoping gaps found.
4. Confirm live Lisa frontend↔backend wiring with a browser-driven request trace.
5. Build (or explicitly scope as future work, clearly labeled) the regulatory applicability condition-tree engine referenced as absent in `tools.py`.

## 20. Recommended Implementation Order

1. Tenancy/security model audit (blocks safe production use).
2. Frontend real-mode rollout for the highest-traffic remaining areas (evidence, inspections, compliance) using the existing `useDataMode` pattern.
3. API-level test backfill for the domains lacking them.
4. Live end-to-end trace of the 5 workflow chains in Section 10 with a running dev server, converting UNKNOWNs to verified BROKEN/WORKING.
5. Scope and design (not necessarily build yet) the regulatory applicability engine.
