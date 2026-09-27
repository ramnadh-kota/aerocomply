> **Note:** This document is the original point-in-time baseline audit. For the current state after the subsequent Lifecycle Integration and Operational Command Center sprints (M22 verification, asset lifecycle timeline, operational state, Command Center consolidation, golden-path test), see [KOTA_AEROSPACE_DEVELOPER_1_LIFECYCLE.md](KOTA_AEROSPACE_DEVELOPER_1_LIFECYCLE.md), which supersedes the completion percentages below.

# KOTA AEROSPACE — Developer 1 Baseline Audit
Digital Aerospace Operations domain (Asset → Configuration → Mission → Flight/Utilization → Inspection → Finding → Maintenance → Work Order → Release → Asset State)

Date: 2026-09-26. Scope: repo at `C:\Users\ramna\Documents\Aerocomply`, evaluated against the Developer 1 roadmap. This supplements (does not replace) existing `docs/FULL_SYSTEM_AUDIT.md`, `docs/ROADMAP_STATUS.md`, `docs/ARCHITECTURE_ASSET_FOUNDATION.md`, and `docs/adr/*`, which already document most of the architecture below — read those before assuming anything here is new.

---

## 0. Headline finding

The Developer 1 domain is **far more built-out than the prompt assumes**. This is not a 90-day greenfield build — nearly every milestone in the roadmap (Asset, Configuration, Mission, Flight, Maintenance, Work Order, Parts, Inspection, Finding, Dashboard) already has a working DB model → service → API → frontend page chain, several with real tests. The in-flight, uncommitted work in the working tree is **Milestone M22 (Work Order Lifecycle)** — a state-machine upgrade to the existing Work Order/Task domain — and it is close to done but not yet verified end-to-end.

The right move is **not** to restart the roadmap from Milestone 1. It is to (a) finish and verify M22, (b) close the specific gaps identified below, in priority order.

---

## 1. EXISTING (built and wired: model → service → API → frontend, at least one test)

| Domain | Model(s) | API | Service | Frontend | Tests |
|---|---|---|---|---|---|
| Asset (generic) | [asset.py](backend/app/models/asset.py) | [assets.py](backend/app/api/v1/assets.py) | asset_service.py, asset_resolution.py | `/assets`, `/assets/[id]` | test_asset_foundation*.py |
| Aircraft (legacy detail) | [aircraft.py](backend/app/models/aircraft.py), aircraft_detail.py | aircraft.py | aircraft_service.py | `/aircraft`, `/fleet/aircraft` | — |
| Drone | drone models via component/battery | drones.py | drone_service.py | `/drones`, `/drones/[id]` | test_drone_operations.py, test_drone_lifecycle_api.py |
| Battery/Component (Configuration) | battery.py, [component.py](backend/app/models/component.py), installation_history.py | (nested in drones.py/aircraft.py) | component_service.py, installation_service.py, battery_service.py | `/components`, `/components/[id]` | test_installation_lifecycle.py, test_installation_concurrency.py |
| Mission | [mission.py](backend/app/models/mission.py) | [missions.py](backend/app/api/v1/missions.py) | mission_service.py | lib/api/missions.ts | frontend/tests/missions-and-work-orders.test.ts (no backend integration test — gap) |
| Flight / Utilization | [flight.py](backend/app/models/flight.py) | nested (no standalone router found) | flight_service.py (`get_utilization`) | — | test_flight_api.py, test_flight_concurrency.py |
| Inspection | inspection_requirement.py | [inspections.py](backend/app/api/v1/inspections.py) | inspection_service.py | `/maintenance/inspections` | test_inspection_lifecycle.py, test_inspection_completion_identity_api.py |
| Finding | [finding.py](backend/app/models/finding.py) (Finding + FindingDisposition) | [findings.py](backend/app/api/v1/findings.py) | finding_service.py | `/findings`, `/findings/[id]` | test_finding_api.py, test_finding_lifecycle.py |
| Maintenance Requirement | maintenance_requirement.py | [maintenance.py](backend/app/api/v1/maintenance.py) | maintenance_service.py | `/maintenance-program` | test_maintenance_service.py |
| Deferred Items (MEL/CDL) | deferred_item.py | deferred_items.py | deferred_item_service.py | `/maintenance/deferred` | test_deferred_item_service.py |
| Work Order + Task | [work_order.py](backend/app/models/work_order.py), [task.py](backend/app/models/task.py) | [work_orders.py](backend/app/api/v1/work_orders.py) | [work_order_service.py](backend/app/services/work_order_service.py) | `/maintenance/work-orders`, `/[id]` | test_work_order_schema.py, test_work_order_deletion_governance.py + new M22 tests (uncommitted) |
| TAT | (uses WorkOrder.due_at) | [tat.py](backend/app/api/v1/tat.py) | tat_service.py | TAT badge on WO detail | test_tat_service.py (pre-existing, verify still matches new logic) |
| Technician | technician_qualification.py | technicians.py | technician_service.py | `/maintenance/technicians` | test_technician_service.py |
| Parts / Inventory / Procurement | part.py, part_requirement.py, inventory_transaction.py, vendor.py, purchase_order.py, warehouse.py | parts.py, inventory.py, procurement.py, purchase_orders.py, receiving.py, vendors.py, warehouses.py | part_service.py + 8 more | `/maintenance/parts`, `/procurement/*` | test_part_service.py + 7 more |
| Release Readiness | (rollup over WO/tasks/evidence/inspection) | release_readiness.py | release_readiness_service.py | `RealReleaseReadinessPanel` on WO detail | test_release_readiness_service.py, test_release_readiness_full_chain.py — **browser-verified** per ROADMAP_STATUS.md |
| Control Center / Dashboard | — | control_center.py | control_center_service.py | `/maintenance/control-center`, `/control-tower`, `/operations`, `/hangar` | test_control_center_service.py |
| Audit / Lifecycle History | audit_event.py, installation_history.py | (via platform/control_center) | audit_service.py | `/audit`, `/platform/audit`, `/tenant/audit` | test_audit_read_api.py, test_audit_immutability.py |
| AOG | (aog events) | aog.py | aog_service.py, aog_recovery_service.py | AOG recovery page | test_aog_service.py, test_aog_recovery_service.py |
| Shared platform (Org/User/RBAC/Tenant) | organization.py, user.py, tenant_entitlement.py | auth.py, users.py, tenant.py, entitlements.py | auth_service.py, tenant_service.py, entitlement_service.py | login/org/platform routes | ~20 dedicated test files |

**Conclusion: Milestones 1 (Asset), 2 (Configuration), 3 (Mission), 4 (Flight/Utilization), 5 (Maintenance), 6 (Parts), 7 (Inspection), 8 (Finding→Maintenance), 10 (Operational State via Asset.status + release readiness), 11 (Dashboard, fragmented) already exist in some working form.** Do not rebuild them from scratch.

---

## 2. PARTIAL (exists but incomplete)

1. **Work Order Lifecycle (M22)** — the state machine, RBAC split (`require_any_permission`), TAT wiring, and rich frontend detail page are implemented in the working tree but **not committed**, and the new migration `0045_work_order_lifecycle.py` has **not been confirmed to apply cleanly** (no `alembic upgrade head` run yet this session). See docs/M22_WORK_ORDER_LIFECYCLE.md.
2. **Mission** — full CRUD+authorize API exists but has **no dedicated backend integration test** (`test_mission*.py` not found). Frontend Mission page existence unconfirmed (may be embedded in drone/ops pages).
3. **Operational Dashboard (Milestone 11)** — fragmented across five overlapping frontend areas (`/dashboard`, `/executive`, `/tenant/dashboard`, `/platform/dashboard`, `/maintenance/control-center`, `/control-tower`, `/operations`, `/hangar`) with no single canonical surface. Functionally covers the roadmap's "what do we have / what's happening / what needs attention" questions, but is not consolidated.
4. **Proactive alerting** — service exists (185 LOC, tested) but **no frontend surface identified**.
5. **Component/Configuration API** — no standalone `components.py` router or `schemas/component.py`; install/removal endpoints appear nested inside `drones.py`/`aircraft.py`. Functionally present, structurally scattered.
6. **Vendor part availability** — service exists, **no test file found**.
7. **Domain event contract (Milestone 12)** — no evidence of an explicit domain-event system (`AssetCreated`, `WorkOrderCompleted`, etc.) for Developer 2 to consume. Currently the only "event" surface is the generic `AuditEvent` log — usable as a substitute but not milestone's intended typed contract.

## 3. BROKEN

Nothing confirmed broken by static reading. The one open risk is **not yet verified**, not confirmed broken: whether migration 0045 applies cleanly and whether the new M22 tests pass (test run in progress at time of writing — see Section 6).

## 4. MISSING

1. Explicit **domain event publication** (Milestone 12 contract) — `KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md` does not exist yet.
2. A single **unified lifecycle timeline view per asset** (Milestone 9) — history is correctly captured (AuditEvent + installation history + WO timestamps + finding dispositions) but there's no one queryable "asset timeline" endpoint/page stitching them together.
3. Dedicated **Mission backend integration test**.
4. Consolidated **Operational Command Center** (single dashboard, Milestone 11) — currently multiple overlapping pages instead of one.

## 5. DUPLICATED / NAMING COLLISIONS (flagged for awareness, not necessarily bugs)

1. **Two "Finding" concepts**: `Finding`/`FindingDisposition` (general MRO) vs `AssessmentFinding` (compliance-assessment-scoped, Developer 2 territory) — intentional per module docstrings, but a name collision to watch when grepping.
2. **Two "Plan" concepts**: commercial `Plan`/`PlanFeature`/`PlanLimit` (subscription catalog) vs the MRO "maintenance plan" concept (no model literally named `MaintenancePlan` — it's `MaintenanceRequirement`). Frontend mirrors the split (`/organization/plan` vs `/maintenance-program`).
3. **Frontend `WorkOrderStatus` enum drift**: `StatusBadge.tsx`'s `WORK_ORDER_STATUS_MAP` still carries legacy `WAITING_PARTS`/`WAITING_INSPECTION` keys alongside the new canonical `ON_HOLD`/`INSPECTION` — dead but harmless (falls back to UNKNOWN). Should be deleted for clarity.
4. **Dual `aircraft_id`/`asset_id` FK pattern** repeated (copy-pasted, not a shared mixin) across `WorkOrder`, `Finding`, `MaintenanceRequirementApplicability` — intentional Phase-1B back-compat per ADR-010/`ARCHITECTURE_ASSET_FOUNDATION.md`, not a bug, but worth eventually consolidating once legacy `aircraft_id` consumers are gone.
5. **Three overlapping authorization primitives** now coexist in `deps.py`: `require_permission` (single RBAC permission), the new `require_any_permission` (RBAC any-of), and `require_feature` (commercial entitlement, separate axis). No bug, but a glossary note would help future contributors.

## 6. ARCHITECTURAL RISKS

- **Uncommitted migration** (`0045_work_order_lifecycle.py`) is the newest in the alembic chain after `0044_plan_limits.py`; anyone pulling `main` right now does not have it. Must be committed together with the model/service/schema changes that depend on it, and verified to apply (running in background — see below).
- `work_order_service.py` grew +518 lines in one change — now the largest service file in the domain, owning both WorkOrder state machine and Task CRUD. Worth a future split (not blocking).
- No standalone `components.py` router means Configuration domain logic is diffused across two unrelated routers — makes it harder to reason about "what can happen to a component" as one surface.
- `ROADMAP_STATUS.md` is now stale for the `work_orders` row (says "no dedicated API test found" — no longer true once M22 tests are committed) — update it when M22 lands.

## 7. RECOMMENDATION — Prioritized execution order

**P0 — Land M22 safely (in progress, not new work):**
1. Run `alembic upgrade head` against a dev DB to confirm migration 0045 applies cleanly; run the full M22 test suite (unit + integration + frontend) and fix any failures.
2. Clean up the dead `WAITING_PARTS`/`WAITING_INSPECTION` StatusBadge keys.
3. Update `docs/ROADMAP_STATUS.md`'s `work_orders` row once verified.
4. Commit the migration + code together (never leave a migration uncommitted after the code that depends on it).

**P1 — Close the smallest, highest-value gaps:**
5. Add a `test_mission_api.py` integration test (Mission has zero backend integration coverage today, unlike every sibling domain).
6. Add a test for `vendor_part_availability_service.py`.

**P2 — Milestone 9/12 (lifecycle history + Developer 2 contract):**
7. Write `KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md` documenting the events Developer 2 should consume (can initially be a thin wrapper describing existing `AuditEvent` rows + payload shapes, rather than a new pub/sub system — cheapest path to the milestone's actual goal of "give Developer 2 reliable facts").
8. Add a queryable "asset lifecycle timeline" endpoint that stitches AuditEvent + installation history + WO milestones + finding dispositions by `asset_id` (Milestone 9) — this is compositional over existing tables, not a new event-sourcing system.

**P3 — Consolidation (lower urgency, cosmetic/structural):**
9. Consolidate the operational dashboard surfaces (Milestone 11) into one canonical Operational Command Center, or explicitly document why the current split (control-center vs control-tower vs operations vs hangar) is intentional.
10. Extract component/configuration endpoints into their own router for clarity.

---

## Completion % by Developer 1 milestone (evidence-based, not aspirational)

| Milestone | % | Basis |
|---|---|---|
| M1 Asset Digital Twin | ~90% | Full model+API+service+frontend+tests |
| M2 Configuration Management | ~75% | Model+service+tests exist; no standalone API surface |
| M3 Mission Management | ~70% | Full CRUD+authorize API; no backend integration test |
| M4 Flight + Utilization | ~80% | Model+service (`get_utilization`)+tests; no standalone router confirmed |
| M5 Maintenance | ~85% | Requirement+deferred items+work order state machine all present |
| M6 Parts + Component Usage | ~85% | Extensive, tested, wired to work orders |
| M7 Inspection | ~85% | Full RII-aware lifecycle, tested |
| M8 Finding → Maintenance | ~85% | Finding/disposition linked to work orders, tested |
| M9 Asset Lifecycle History | ~40% | Data exists (audit+installation history+timestamps) but no unified queryable timeline |
| M10 Operational State | ~75% | Asset.status + release readiness rollup exist; not a single explicit state machine doc |
| M11 Operational Command Center | ~50% | Multiple real but unconsolidated dashboards |
| M12 Developer 1→2 Contract | ~15% | AuditEvent exists as a substitute; no typed domain-event doc/system |

---

## Next 5 highest-value tasks (starting point for execution)

1. Verify migration 0045 applies and the M22 test suite passes; fix any failures (blocking — protects work already done).
2. Remove dead `WAITING_PARTS`/`WAITING_INSPECTION` frontend enum keys.
3. Write `test_mission_api.py` (closes the one glaring test gap in an otherwise-tested domain set).
4. Write `KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md`.
5. Build the asset lifecycle timeline endpoint (composes existing tables; no new architecture).
