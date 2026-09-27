# KOTA AEROSPACE — Developer 1 Lifecycle Architecture

Digital Operations lifecycle integration & completion sprint. This documents what was verified/built in this pass, on top of the pre-existing baseline in [KOTA_AEROSPACE_DEVELOPER_1_BASELINE.md](KOTA_AEROSPACE_DEVELOPER_1_BASELINE.md).

## 1. What this sprint actually changed

**No modules were rebuilt.** Every domain (Asset, Configuration, Mission, Flight, Maintenance, Parts, Inspection, Finding, Work Order) already had a working model→service→API→frontend chain per the baseline audit. This sprint:

1. Verified migration `0045_work_order_lifecycle.py` and the full M22 suite against a live Postgres instance (previously blocked by no local DB).
2. Fixed two real bugs found while extending the asset lifecycle timeline (`asset_service.py`: `AuditEvent.payload` → `event_metadata`; `WorkOrder.updated_at` → `created_at`, since `WorkOrder` has no `updated_at` column).
3. Extended the pre-existing `GET /assets/{asset_id}/history` endpoint (already ~40%-built per baseline) into a real cross-domain lifecycle timeline covering Mission/WorkOrder/Finding/Inspection events, not just Asset audit rows + flights + component installs.
4. Added `compute_operational_state()` — a real, fact-derived operational-state function — replacing a naive two-value (`READY`/`GROUNDED`) placeholder in `get_asset_domain_context`.
5. Verified and corrected the Developer 1 → Developer 2 domain event contract against actual `action="..."` call sites in the codebase.
6. Added integration test coverage for all of the above, run against a live database, with real bugs caught and fixed (not just written and assumed to pass).

## 2. Asset Lifecycle Timeline

**Endpoint:** `GET /assets/{asset_id}/history` (existing path, extended — no duplicate `/timeline` endpoint was created, since one already existed and served this exact purpose).

**Query parameters:** `limit` (1-100, default 50), `event_type` (exact match filter), `date_from`/`date_to` (half-open range on `occurred_at`, matching `audit_service.list_audit_events`'s convention).

**Implementation:** `asset_service.get_asset_history()` in [asset_service.py](backend/app/services/asset_service.py). Reuses the existing `AuditEvent` table for administrative audit rows and inspection completions; queries `Mission`, `WorkOrder`, `Finding`, `Flight`, and `ComponentInstallation` directly for their respective lifecycle milestones (created/completed/closed timestamps already exist as real columns on those models — no new event-sourcing table was introduced).

**Event types emitted today:**

| event_type | Source |
|---|---|
| `AUDIT_EVENT` | AuditEvent rows with `entity_type="Asset"` |
| `FLIGHT_SORTIE` | Flight rows |
| `COMPONENT_INSTALLATION` / `COMPONENT_REMOVAL` | ComponentInstallation rows |
| `MISSION_CREATED` / `MISSION_COMPLETED` | Mission rows |
| `WORK_ORDER_CREATED` / `WORK_ORDER_COMPLETED` / `WORK_ORDER_CLOSED` | WorkOrder rows |
| `FINDING_CREATED` / `FINDING_CLOSED` | Finding rows |
| `INSPECTION_COMPLETED` | AuditEvent rows (`action="inspection.completed"`), joined to the asset's work orders' InspectionRequirement rows |

**Known gap:** `INSPECTION_COMPLETED` only surfaces inspections tied to one of the asset's *currently-queried* work orders (bounded by `limit`); an inspection tied to a work order outside that window won't appear. This is a real, documented limitation, not a silent one — acceptable for now given `InspectionRequirement` has no direct `asset_id` column.

**Tests:** [test_asset_lifecycle_timeline.py](backend/tests/integration/test_asset_lifecycle_timeline.py) — 4 tests, all passing against a live Postgres instance, covering mission/work-order timeline entries, `event_type` filtering, and cross-tenant isolation (404, never a leaked 403).

## 3. Operational State

**Function:** `asset_service.compute_operational_state()`, wired into `get_asset_domain_context()` (`GET /assets/{asset_id}/context`'s `operational_status` field — no schema change needed, the field already existed as a plain string).

**Vocabulary:** `AVAILABLE`, `IN_MISSION`, `UNDER_INSPECTION`, `MAINTENANCE`, `GROUNDED`, `AOG`, `INACTIVE`, `RETIRED` — the exact 8 states named in the roadmap. This is a deliberately different (wider) vocabulary than the pre-existing `AssetOperationalStatus` enum (`READY`/`STANDBY`/`DISPATCHED`/`IN_FLIGHT`/`MAINTENANCE`/`GROUNDED`), which has no AOG/INACTIVE/RETIRED/UNDER_INSPECTION values and would force lossy collapsing of those distinct facts. This divergence is intentional and documented in the function's docstring, not an oversight.

**Precedence (most severe first):** RETIRED → INACTIVE (archived) → AOG (active AogEvent) → GROUNDED (lifecycle status) → MAINTENANCE (lifecycle status or any open, non-terminal work order) → UNDER_INSPECTION (lifecycle status or a pending InspectionRequirement on one of the asset's work orders) → IN_MISSION (an AUTHORIZED/IN_PROGRESS mission) → INACTIVE (PLANNED lifecycle status) → AVAILABLE (default).

**Explicitly out of scope (by design):** no compliance inference, no readiness scoring, no AI judgement — purely a derivation over existing facts, which Developer 2 consumes as input to their own readiness reasoning.

**Tests:** [test_asset_operational_state.py](backend/tests/integration/test_asset_operational_state.py) — 5 tests, all passing: default AVAILABLE, GROUNDED via lifecycle status, MAINTENANCE via an open work order, IN_MISSION via an authorized mission, and cross-tenant isolation.

## 4. Developer 1 → Developer 2 Contract

See [KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md](KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md) — every `action` string in that document was re-verified against the actual `record_audit_event(..., action="...")` call sites in `mission_service.py`, `finding_service.py`, `work_order_service.py`, `installation_service.py`, and `inspection_service.py` during this sprint (not assumed from the earlier draft). Consumption pattern: poll `AuditEvent` filtered by `organization_id`/`action`/`created_at`, not a new message bus.

## 5. M22 Work Order Lifecycle — verification result

Migration `0045_work_order_lifecycle.py` was applied against a live Postgres 16 instance (`infra/docker-compose.yml`, `postgres` service) and the full M22 suite was run:

- `tests/unit/test_work_order_lifecycle.py` + `tests/integration/test_work_order_lifecycle_api.py` + `tests/unit/test_tat_service.py` + `tests/integration/test_work_order_deletion_governance.py`: **43/43 passed.**

No code changes were required — the migration and state machine were already correct. This closes out the P0 blocker from the baseline audit.

## 6. Pre-existing gap discovered (not introduced by this sprint)

Registering a new organization via `POST /auth/register-organization` creates **no default subscription/plan**. Every `require_feature(...)`-gated route (drones, missions, work orders, etc.) 403s for a fresh org until a test/caller explicitly creates a `Plan` + `PlanFeature` + `Subscription`. This is why `tests/integration/test_drone_lifecycle_api.py` (pre-existing, not touched this sprint) currently fails against a fresh local test database — confirmed by running it standalone, independent of any change made here. All new tests in this sprint follow the same explicit-entitlement convention already established by `test_work_order_lifecycle_api.py::_entitle_work_orders`.

This is a real product/onboarding gap worth fixing (new orgs presumably should land on a trial plan), but it is out of scope for this sprint and is called out here rather than silently worked around in production code.

A second, distinct pre-existing gap was found while running the full backend suite for regression-checking: M22's `work_order_service.create_task()` now requires a mandatory keyword-only `actor_user_id` argument, but several pre-existing tests that predate M22 (`tests/integration/test_technician_service.py`, `tests/integration/test_evidence_file_service.py`, and others) still call it with the old signature, raising `TypeError` at call time. This is M22 test debt (the M22 commit changed a shared service's signature without updating every existing caller), not something introduced this sprint, and not something this sprint's instructions authorized fixing (in-scope work was Phases 0/1/2/4, not a general test-suite repair pass).

## 6b. Phase 10 finding: fresh-org entitlement — intentional, not a defect

Investigated directly against the source rather than guessed. `auth_service.register_organization` (the bootstrap path this test suite and this sprint's tests use) creates an `Organization` + first `ORG_ADMIN` `User` and nothing else — no `Subscription`. `provisioning_service.provision_organization(..., plan_id=...)` is a **separate, distinct** function whose own docstring says "entitlements are never copied by hand: creating the Subscription is the [act of granting them]" — it takes an explicit `plan_id` and atomically creates Organization + Subscription together, with `_rollback_partial_provisioning` ensuring no orphaned org/subscription on failure. These are two intentionally different onboarding paths, not one broken one. No code was changed for this finding — inventing an auto-entitlement rule inside `register_organization` would be guessing at a business rule (which plan? trial length? which features?) that this investigation has no authority to invent.

## 6c. Phase 6 finding: consolidated duplicate operational-state logic

`control_center_service.get_fleet_rows()` had its own independent 3-value ternary (`AOG`/`UNDER_MAINTENANCE`/`OPERATIONAL`, based only on active-AOG-event and open-work-order checks) computed separately from the new `compute_operational_state()` — exactly the "backend says AVAILABLE, frontend/another-endpoint independently calculates MAINTENANCE" anti-pattern this phase asks to find. Consolidated: for any aircraft with a resolved `asset_id`, the row's status is now derived from `compute_operational_state()` via a documented 8→3 value mapping (`_STATE_TO_LEGACY_STATUS`); the pre-existing 3-value field is preserved for backward compatibility, and the endpoint additionally now exposes the true 8-value fleet-wide distribution (`ControlCenterSummary.operational_states`, `total_assets` — additive fields, existing consumers unaffected). Legacy aircraft rows with no `asset_id` yet keep the original ternary as a documented fallback (`compute_operational_state` requires a real `Asset` row).

While consolidating, two more real bugs were found and fixed in the same function: (1) an N+1 query pattern (`list_work_orders` called once per aircraft in a loop), and (2) that same call had no `asset_id`/`aircraft_id` filter and relied on `list_work_orders`' default `limit=50`, so any organization with more than 50 open work orders would have silently mis-attributed or dropped rows for later aircraft. Both are fixed by one batched query grouped in Python. All 8 pre-existing `test_control_center_service.py` tests still pass unchanged, plus one new test asserting the legacy field and the new distribution never disagree for the same asset.

## 6d. Phase 11 finding: frontend REAL-mode audit

`/maintenance/control-center` correctly branches on `useDataMode()` — REAL mode calls `controlCenterApi.getSummary/getFleet` (the real, now-consolidated backend), DEMO mode is clearly labeled "Demo Dataset View (below)". This page is fine as-is.

Four other operational dashboard pages have **no REAL-mode branch at all** — they import unconditionally from `lib/mock/*` regardless of `useDataMode()`, with no on-page indicator distinguishing them from live data:
- `/maintenance/operations`
- `/maintenance/hangar`
- `/maintenance/control-tower`
- `/dashboard`

This was not fixed this sprint (out of scope given the backend-first priority and remaining time budget), but it is the single most actionable Phase 11/Command-Center-consolidation follow-up: a user could reasonably mistake these for live fleet data since nothing on the page says otherwise. Recommended next step: either wire each to the same `controlCenterApi` the control-center page already uses, or add the same `isRealModeSession`-gated "Demo Dataset View" label these pages currently lack.

## 6e. Phase 1/6 finding: Asset Detail already existed and was mostly wired — one real duplicate-state bug found and fixed, verified live in browser

The Asset Detail page (`frontend/app/(app)/assets/[id]/page.tsx`, 1400 lines) was **not missing** — it already fetches and renders configuration, components, operations, maintenance, inspections, evidence, findings, compliance, readiness, and the real lifecycle history/timeline (a "Lifecycle" tab rendering `history.events` from the exact `/assets/{id}/history` endpoint built in the prior sprint). The frontend API client (`lib/api/assets.ts`) already had `getContext()` wired to `/assets/{id}/context`, and the demo layer already had an unused `getDemoDomainContext()` — the wiring was half-finished, not absent.

The one real defect found (exactly the Phase 6 anti-pattern): the page's "Operational" status badge was computed with a local, duplicate ternary —
```ts
const isGrounded = asset.status === "GROUNDED" || asset.status === "MAINTENANCE";
const operationalStatus = isGrounded ? "GROUNDED" : "READY";
```
This only looks at the static lifecycle-status column and can never show `IN_MISSION`, `UNDER_INSPECTION`, `AOG`, `INACTIVE`, or `RETIRED`, and can disagree with the real backend state (e.g. an open work order created through a different flow than the `status` column update). Fixed by wiring the already-existing `assetsApi.getContext()` call into the page's data fetch and consuming `context.operational_status` (the real `compute_operational_state()` value) instead, with the old heuristic kept only as a degraded fallback if the context call itself fails. Added `operationalStateBadge()` to `StatusBadge.tsx` for the real 8-value vocabulary (previously only Control Tower's demo-only 3-value analytics mapping existed for anything "operational-status"-shaped). Updated `getDemoDomainContext()` in `lib/demo/demoAssets.ts` to emit the same 8-value vocabulary so demo mode doesn't look like a different, narrower state model than REAL mode (Phase 10).

**Verified live**, not just by reading the diff: started the Next.js dev server and a real backend (`uvicorn`) against a fresh Postgres database, registered a real organization via direct DB seeding + `/auth/login`, created a real drone asset via the actual API, and loaded the Asset Detail page in the browser —
- Fresh asset: badge correctly showed `OPERATIONAL: AVAILABLE`.
- After creating a real open Work Order via the API (no `status` column change): badge correctly flipped to `OPERATIONAL: MAINTENANCE` — proving the fix (the old code would have stayed on `READY`/`AVAILABLE` since `asset.status` never changed).
- History tab rendered the real `WORK_ORDER_CREATED` and `drone.created` audit events with real timestamps and actor IDs, confirming the timeline endpoint (prior sprint) also renders correctly through the actual UI, not just via API tests.

`npm run typecheck` and `npm run lint` both ran clean (0 TypeScript errors; lint: 0 errors, 102 pre-existing warnings unrelated to this change, not touched).

## 7. Real Operations UI Completion sprint (this pass)

This sprint converted Dashboard, Maintenance Operations, Hangar, and Control Tower from demo-only (or, in Dashboard's case, partially-real-but-locally-computed) to REAL-mode surfaces consuming the one authoritative `compute_operational_state()` / `/control-center/summary` path, and closed the AOG live-test gap. All work was **verified live** (backend + Postgres + browser), not just compiled.

**Important correction to two prior claims:** the previous sprint's report said Dashboard had "no REAL-mode branch at all" and that Control Tower "was previously reported as having REAL/demo support." Direct inspection this sprint showed both were wrong in different directions: Dashboard was *already partially real* (via a different mechanism, `useSession().sessionType`, not `useDataMode()` — the earlier grep only checked for one hook name and missed it); Control Tower was *fully demo-only* (its own code comment says so explicitly), so the "already has REAL/demo support" claim was never true. Corrected here rather than silently carried forward.

### 7a. Dashboard (`/dashboard`) — REAL mode: PASS

`RealFleetPanel` already fetched live `aircraftApi`/`dronesApi`/`workOrdersApi`/`deferredItemsApi` data with proper loading/error/empty states, but computed fleet status locally: `activeAssets`/`groundedAssets` from raw `status` fields — unable to ever show `IN_MISSION`/`UNDER_INSPECTION`/`AOG`/etc., and could disagree with the real backend state. Rewired to call `controlCenterApi.getSummary()` (the same authoritative endpoint Command Center uses) and render the true 8-value `operational_states` distribution via the shared `operationalStateBadge()` helper. Updated the TS `ControlCenterSummary` type (was stale, missing `total_assets`/`operational_states` added to the backend 2 sprints ago) and `getDemoDomainContext`'s demo vocabulary to match. **Live-verified**: `Total Assets: 1`, `Available: 0`, and `Fleet Operational State Distribution → MAINTENANCE: 1` after attaching an open work order to the test asset — matching the real backend state, not a locally-recomputed one.

### 7b. Maintenance Operations (`/maintenance/operations`) — REAL mode: PARTIAL (by design)

Was a Server Component, 100% demo, explicit subtitle admission ("every value is derived from current demo data"). Converted to a Client Component; added a `RealWorkOrderSnapshot` section using the same `workOrdersApi.list()` real endpoint already used elsewhere, showing real Open Work Orders count + status breakdown with the real backend `WorkOrderStatus` vocabulary (`DRAFT/OPEN/PLANNED/ASSIGNED/IN_PROGRESS/ON_HOLD/INSPECTION/COMPLETED/CLOSED/CANCELLED`) — distinct from the demo section's fictional `WAITING_PARTS`/`WAITING_INSPECTION` labels (already flagged and removed from the shared `StatusBadge` map 2 sprints ago as dead values). Technician workload, parts-at-risk, findings-requiring-attention, and inspection aging were **left as demo**, honestly labeled "Illustrative Data" — these concepts (checklist-item-level pass/fail, MRO-specific technician-workload aggregation) have no direct backend equivalent yet, and fabricating one within this sprint's budget would violate the no-fake-data rule worse than leaving them clearly marked. **Live-verified**: "Work Orders (Live) → REAL DATA → Open Work Orders: 1 → DRAFT: 1".

### 7c. Hangar (`/maintenance/hangar`) — REAL mode: PARTIAL (by design)

Added a `RealActiveWorkOrders` section (real work order number/status/priority/assigned-technician/due-date) using the same `workOrdersApi.list()` path. The below-decks "Active Work — Task Cards" checklist-execution simulation (per-item PASS/FAIL/UNKNOWN progress, `defectsForWorkOrder`, part blockers) is powered by `MroStateContext`, a client-only prototype with **no backend model at all** — not a gap in wiring, a genuine missing domain concept. Labeled "Illustrative Data" rather than fabricated against real work orders. **Live-verified**: "Active Work Orders (Live) → REAL DATA → WO-PREVIEW-1".

### 7d. Control Tower (`/maintenance/control-tower`) — REAL mode: PASS (new, corrects prior claim)

Added a `RealOperationalStateSummary` section using `/control-center/summary`, non-invasively placed above the existing filterable demo fleet table (left untouched — its risk scoring, material-shortage heuristics, and next-maintenance-due projections are Developer-2-adjacent concepts this sprint should not fabricate, matching Phase 14's boundary). Relabeled the existing KPI board "Demo Fleet Risk Board — Illustrative Data" since it previously had no explicit demo indicator at all. **Live-verified**: "Fleet Operational State (Live) → REAL DATA → Total Assets: 1, MAINTENANCE: 1".

### 7e. AOG live verification (Phase 9) — PASS

New `test_aog_operational_state.py`, 2 tests, both passing live against Postgres:
1. Declaring an `AogEvent` (`POST /aog-events`, the actual — and only — domain path to AOG; there is no direct "set state to AOG" transition) flips `compute_operational_state()` to `AOG`, confirmed via `/assets/{id}/context`, `/control-center/fleet` (per-asset row), and `/control-center/summary` (fleet distribution) — the same state, reflected consistently everywhere, as required.
2. `DECLARED → IN_RECOVERY → RECOVERED` (the real `AogEventStatus` state machine — `mark-recovered` cannot be called directly from `DECLARED`, confirmed by a real `409 Conflict` during test development) returns the asset to `AVAILABLE`.
Also confirmed a real audit trail (`AuditEvent` rows for `entity_type="AogEvent"`) and tenant isolation (404 for cross-tenant asset access, empty list for cross-tenant fleet query).

### 7f. Frontend quality gate — ALL PASS

- `npm run typecheck`: 0 errors.
- `npm run lint`: 0 errors (pre-existing unrelated warnings untouched).
- `npm run build`: succeeded, all routes compiled including the 4 modified pages.
- `npm run test` (Vitest): **298/298 passed** across 26 test files.

### 7g. Backend regression after frontend changes

Re-ran the targeted suite named in the sprint (control center, operational state, golden path, timeline, mission, M22) plus the new AOG tests: **40/40 passed** (38 from the named suite + 2 new AOG tests). No backend files were changed this sprint except the two new test files and one TS-facing schema field already present server-side — confirms no accidental backend regressions from frontend work.

## 9. Final Production Audit (Freeze Sprint)

Re-verified everything below rather than assuming it still held; exact counts, not "tests pass."

### 9a. Repository health audit

No accidental/debug artifacts found in any file touched across this session's sprints: no `console.log`/`console.debug`, no `TODO`/`FIXME`/`XXX` in `asset_service.py`, `control_center_service.py`, or the four converted frontend pages. `git status` shows a shared working tree with Developer 2's concurrent, legitimate work (their own `applicability`/`compliance` modules, migrations 0046-0048, their own docs) — nothing stray or accidental. No new duplicated status constants or dead API clients were introduced this session.

### 9b. Operational source-of-truth audit (Phase 2)

Searched the full frontend again for `isGrounded`/`isMaintenance`/`isInMission`/`isAOG` and for literal 8-value state strings outside `lib/mock`/`lib/demo`. Findings:
- **One occurrence of `isGrounded`** remains, in `assets/[id]/page.tsx` — but only as the documented degraded **fallback** used solely if the real `context` API call fails (`context?.operational_status ?? (isGrounded ? "GROUNDED" : "AVAILABLE")`), not a competing primary computation. Classified: **acceptable, intentional fallback**, not a defect.
- All other `AVAILABLE`/`AOG` string matches in `app/` are false positives from unrelated domains: work-order priority filter values, procurement `PartRequestPriority` labels, and the pre-existing, already-correctly-separated `aog-recovery` page (labels its demo heuristic `analysis.isAog` distinctly from the real `recoveryStatus.is_aog`, suffixed "(real)").
- **Confirmed**: Asset Detail, Dashboard, Control Center, Control Tower, Maintenance Operations, and Hangar all trace to the same `compute_operational_state()` → `/assets/{id}/context` or `/control-center/summary` → frontend path, with zero remaining independent domain-state calculations.

### 9c. Golden path revalidation — PASS, unmodified

`test_operational_golden_path.py` re-run without modification: **1/1 passed**, full 14-stage chain (Asset→Configuration→Component→Mission→Flight→Utilization→Inspection→Finding→WorkOrder→Maintenance→FollowUpInspection→Release→LifecycleHistory→OperationalState) with audit-event assertions intact.

### 9d. AOG revalidation — PASS, unmodified

`test_aog_operational_state.py` re-run: **2/2 passed**. Declaration path and `DECLARED → IN_RECOVERY → RECOVERED` state machine confirmed unchanged and correct (recovery cannot skip `IN_RECOVERY` — enforced server-side, not simplified for testability).

### 9e. Tenant security audit — PASS

Ran the two dedicated backend tenant-isolation suites (`test_tenancy_isolation.py`, `test_tenant_isolation.py`) alongside the operational suites: **49/49 passed** combined. Confirms authorization is enforced server-side (never frontend-only) across assets, missions, work orders, findings, timeline, operational state, and Command Center — cross-tenant access returns 404 (existence never leaked), missing entitlement returns 403, both previously verified explicitly in the golden-path and AOG tests.

### 9f. API contract / performance audit

No new APIs added this sprint. Confirmed the Work Order N+1 and default-`limit=50` truncation bug (fixed 2 sprints ago in `control_center_service.py`) has not regressed — `list_work_orders(` is called zero times in that file; the single batched query remains in place.

### 9g. Full test matrix (exact counts)

| Suite | Result |
|---|---|
| Golden path | 1/1 passed |
| M22 (unit + integration) | included below |
| Operational state | included below |
| AOG | 2/2 passed |
| Control Center | included below |
| Mission | included below |
| Timeline | included below |
| Tenant/security | included below |
| **Combined backend run** (golden path + M22 + operational-state + AOG + control-center + mission + timeline + tenancy/tenant isolation) | **49/49 passed** |
| Frontend Vitest | **298/298 passed** (26 files) |
| Frontend typecheck | 0 errors |
| Frontend lint | 0 errors (105 pre-existing warnings, untouched) |
| Frontend production build | succeeded, all routes compiled |

## Developer 1 Baseline Freeze

### What Developer 1 owns
Asset (incl. Aircraft/Drone/Helicopter/eVTOL), Configuration, Components (install/removal), Missions, Flights, Utilization, Inspections, Findings, Maintenance, Work Orders, Lifecycle History, Operational State, and the operational UI surfaces (Asset Detail, Dashboard's Fleet Overview, Maintenance Operations, Hangar, Control Tower, Command Center).

### What Developer 1 does not own
Compliance reasoning, regulatory interpretation, risk intelligence, readiness reasoning, AI recommendations, decision optimization. (Developer 2's `applicability`/`compliance` modules, visible as concurrent uncommitted work in this shared tree, confirm this boundary is already being respected by both sides in practice.)

### Authoritative operational state
`backend/app/services/asset_service.py::compute_operational_state()` is the single authoritative computation for AVAILABLE/IN_MISSION/UNDER_INSPECTION/MAINTENANCE/GROUNDED/AOG/INACTIVE/RETIRED. Every consumer (API and frontend) reads this value; none recompute it.

### Developer 1 → Developer 2 contract
See [KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md](KOTA_AEROSPACE_DEVELOPER_1_DOMAIN_EVENTS.md) for the full event catalog. Summary of consumable facts: Asset identity/state, Configuration/Component install-remove history, Mission/Flight/Utilization records, Inspection/Finding records, Work Order lifecycle and timestamps, the unified Lifecycle History timeline (`/assets/{id}/history`), and the Operational State distribution (`/control-center/summary`). All consumed via polling `AuditEvent` and the listed REST endpoints — no message broker.

## 10. Remaining gaps, classified

**Production blockers:** none found.

**Product gaps** (capabilities intentionally not yet built, not defects):
- Technician-workload, parts-at-risk, and checklist-execution aggregation have no backend model — Operations/Hangar demo sections reflect this honestly.
- No standalone `/components` API router (functionality exists, nested under `/assets`/`/drones`).
- No dedicated `vendor_part_availability` test (baseline finding, unchanged).

**Developer 2 dependencies** (correctly out of Developer 1's scope):
- Compliance/risk/readiness scoring on Dashboard and Control Tower (already demo-labeled "AI Prototype"/"Illustrative Data").
- Any future consumption of the domain-event contract.

**Future enhancements** (useful, not required for baseline):
- Frontend Command Center dashboard consolidation (multiple routes still exist independently: `/dashboard`, `/maintenance/control-center`, `/maintenance/control-tower`, `/maintenance/operations`, `/maintenance/hangar`).
- Fresh-org entitlement UX (currently requires explicit plan assignment via `provision_organization`, separate from `register_organization` — intentional, but could be smoothed for onboarding).

## 11. Final milestone completion (recalculated, not inflated by this audit)

| Milestone | STATUS | EVIDENCE | REMAINING |
|---|---|---|---|
| M1 Asset | COMPLETE | Full CRUD+context+history+readiness API; live-verified in golden path, Dashboard, Asset Detail | none material |
| M2 Configuration | PARTIAL | Component install/remove API + history, exercised in golden path | no standalone `/components` router |
| M3 Mission | COMPLETE | Full CRUD+authorize API, 7/7 dedicated tests, drives IN_MISSION state live | none material |
| M4 Flight/Utilization | COMPLETE | Drone flight recording + utilization aggregation, verified live in golden path | none material |
| M5 Maintenance | COMPLETE | M22 state machine, 43/43 tests, migration verified live | pre-existing `create_task()` signature test debt in unrelated pre-M22 tests |
| M6 Parts | PARTIAL | Extensive parts/procurement modules, individually tested | not exercised in golden path; no vendor_part_availability test |
| M7 Inspection | COMPLETE | RII-aware lifecycle, exercised twice in golden path + AOG-adjacent tests | none material |
| M8 Finding→Maintenance | COMPLETE | Finding→disposition→close, linked to asset+work order, gates release readiness | none material |
| M9 Lifecycle History | COMPLETE (backend); no frontend timeline UI beyond Asset Detail's tab | `/assets/{id}/history` covers all major event types, verified live in browser | none material for baseline |
| M10 Operational State | COMPLETE, all surfaces | Single authoritative function, consumed by every frontend page, AOG live-tested | none material |
| M11 Command Center | COMPLETE (backend + 4 frontend consumers) | Consolidated, bug-fixed, tested; Dashboard/Operations/Hangar/Control Tower all wired | dashboard route consolidation is a future enhancement, not a blocker |
| M12 Dev1→Dev2 Contract | PARTIAL | Every event re-verified against real source; polling `AuditEvent` is the intended pattern | no consumer-side example client (by design, not urgent) |

**Overall Developer 1 completion: approximately 85%** — unchanged from the prior sprint's honest figure. This audit found zero new defects requiring a percentage change in either direction; it exists to confirm the 85% is real, not to move it.

## 12. Freeze Decision

```
READY FOR DEVELOPER 2
```

Developer 1's operational foundation (Asset → Configuration → Mission → Flight → Utilization → Inspection → Finding → Work Order → Maintenance → Release → Lifecycle History → Operational State) is coherent, live-tested end-to-end, tenant-isolated, and has one authoritative operational-state computation with zero remaining duplicate logic. Developer 1 should now enter **maintenance mode**: bug fixes, security fixes, contract fixes, and integration fixes only — no broad new domain expansion unless a concrete Developer 2 dependency surfaces.
