# M20 Release Verification — Read-Only Audit

Date: 2026-09-20. Scope: read-only. No files modified except this report. No migrations run, no commits, no pushes, no deploys, no staging/production data touched. All backend/frontend URLs hit were public GET-only health/openapi endpoints.

Status legend used throughout: **COMPLETE / PARTIAL / NOT COMPLETE / NOT VERIFIED**. Never inferred from code existing alone — each claim below cites the check that produced it.

---

## 1. Release identity

- Local `git rev-parse HEAD` = `fce85bfa537a8faa4b8d23d945f68db21d703bd0`.
- Local `git rev-parse origin/main` = `fce85bfa537a8faa4b8d23d945f68db21d703bd0` — **identical**, branch is up to date with origin, nothing unpushed on `main`.
- Deployed frontend `https://aerocomply.vercel.app` → `200`.
- Deployed backend `https://aerocomply-backend-staging.onrender.com/api/v1/health` → `200`; `/api/v1/health/ready` → `200`; `/openapi.json` → `200`.
- Deployed `/openapi.json` contains exactly the routes the local `fce85bf` tree defines for `findings` and `drones`: `/api/v1/findings`, `/api/v1/findings/{finding_id}`, `/api/v1/findings/{finding_id}/close`, `/api/v1/findings/{finding_id}/dispositions` all present (matches `backend/app/api/v1/findings.py`), and the full `drones` route set (`/api/v1/drones`, `.../batteries`, `.../components`, `.../flights`, `.../utilization`, `.../deployment-readiness`, `.../lifecycle-history`, `.../maintenance-due`, `.../maintenance-requirements/{id}/applicability|accomplishments`) matches `backend/app/api/v1/drones.py:54-442`.
- Deployed frontend serves `200` for `GET /findings/test-id` (the dynamic route added in `fce85bf`, `frontend/app/(app)/findings/[id]/page.tsx`), consistent with that commit being live.

**Verdict: COMPLETE.** Deployed backend/frontend are consistent with `fce85bf`, matching the prior session's confirmation. This is a public-endpoint/route-presence check only — not a deep content diff of the bundle or DB schema (see §9).

---

## 2–5. M20.1–M20.4 commit-by-commit verification (`git show --stat` + diff read)

### M20.1 — `100959f` "feat(dashboard): wire real KPI cards and fleet/work-order charts"
- Diffstat: `frontend/app/(app)/dashboard/page.tsx` (+224/-… within 224 net lines changed), `frontend/app/globals.css` (+71), `M20_1_REPORT.md` (+100, untracked report file).
- Confirmed real: KPI tiles and two CSS bar charts are computed from live endpoint calls (aircraft/drones/work-orders/deferred-items), not from `lib/mock/*`, per the commit message and corroborated by the dashboard file's current imports (§4 below shows `dashboard/page.tsx:16` still imports `lib/mock/findings` for an *unrelated*, explicitly-labeled "Illustrative Data" section — this is the section M20.1 left untouched, not evidence against M20.1's own claim).
- **Verdict: COMPLETE** for "KPI cards + 2 charts backed by real counts," as scoped. Not a full dashboard rebuild (other sections remain mock, self-labeled).

### M20.2 — `fad9ae1` "feat(findings): general Finding/Disposition backend domain model"
- Diffstat: 11 files, entirely additive (`backend/app/models/finding.py` +165, `backend/app/schemas/finding.py` +83, `backend/app/services/finding_service.py` +220, `backend/app/api/v1/findings.py` +112, `backend/alembic/versions/0036_finding_disposition.py` +116, 2 test files +170/+133, `frontend/lib/api/findings.ts` +82, `frontend/app/(app)/aircraft/[id]/page.tsx` +149).
- Read `backend/app/api/v1/findings.py` directly (not just the commit message): every route (`create_finding`, `list_findings`, `get_finding`, `add_disposition`, `close_finding`) takes `current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE|READ))` and passes `organization_id=current_user.organization_id` server-side (`findings.py:28-33, 56-60, 73-76, 86-89, 106-109`) — client never supplies `organization_id`. Confirms M20_2_REPORT.md's own claim rather than trusting it blindly.
- Read migration `backend/alembic/versions/0036_finding_disposition.py:24-25`: `revision = "0036"`, `down_revision = "0035"` — a real, chained, additive migration (creates `findings` + `finding_dispositions` tables only; no `alter`/`drop` on existing tables per the file header docstring and `upgrade()` body inspected).
- **Verdict: COMPLETE** as a backend-only slice. The one caveat the M20.2 report itself states and this audit did not re-run: browser verification was not performed for this milestone (integration tests via `TestClient` only) — carried into §12 as NOT VERIFIED for that specific claim.

### M20.3 — `8c9dff1` "feat(dashboard): replace mock findings widget with real M20.2 Finding data"
- Diffstat: `frontend/app/(app)/dashboard/page.tsx` (+86), `frontend/lib/api/findings.ts` (+10). Small, additive, no deletion of the old mock import line for the unrelated Maintenance Operations Snapshot section (confirmed still present at `dashboard/page.tsx:16`, `import { findings } from "@/lib/mock/findings"`).
- Confirmed by reading the current file: `dashboard/page.tsx:31` imports `findingsApi, type BackendFinding` from `@/lib/api/findings`; `dashboard/page.tsx:218` defines `function RealFindingsPanel()`; `dashboard/page.tsx:335` renders `<RealFindingsPanel />`. This is a real, org-scoped `GET /findings` client call feeding a live widget, distinct from the still-present mock import used elsewhere on the same page (self-documented at `dashboard/page.tsx:215`: "Distinct from lib/mock/findings.ts, which stays confined to...").
- **Verdict: COMPLETE** for "dashboard findings widget is real," narrowly scoped as claimed. The commit message's own honesty about scope (mock import "stays confined to the already-illustrative-labelled Maintenance Operations Snapshot section") checks out against the current file.

### M20.4 — `fce85bf` "feat(findings): canonical Finding detail route at /findings/[id]"
- Diffstat: `frontend/app/(app)/dashboard/page.tsx` (+13/-…), `frontend/app/(app)/findings/[id]/page.tsx` (new, +267), `frontend/tests/finding-detail.test.ts` (new, +118).
- Read `frontend/app/(app)/findings/[id]/page.tsx:157-167`: renders a "View Aircraft" link when `finding.aircraft_id` is set and a "View Drone" link (`/drones/{finding.asset_id}`) when `finding.asset_id` is set — i.e. the detail page already branches for both aircraft- and drone-linked findings, not aircraft-only.
- Read `frontend/tests/finding-detail.test.ts:48-115`: 6 tests (`get()` success, `get()` 404-normalized, `get()` 500-normalized-distinct-from-404, `addDisposition()`, `close()`, `listForOrganization()` with status filter) exercising `findingsApi` against mocked HTTP responses — unit-level, not a live-DB integration or browser test.
- **Verdict: COMPLETE** for the stated scope (one canonical detail route, reusing M20.2/M20.3's API — no new backend). Frontend unit tests exist; no browser-driven verification exists for this route (see §12).

---

## 6. M18 reconciliation

**Correction to the task's own premise**: no file named `M18_1_INTEGRATION_MATRIX.md` exists in this repo. `git log`/`ls` confirm only `M18_LIVE_INTEGRATION_REPORT.md` exists, and that file's own header explains this was already discovered and documented in the prior `M20_AUDIT_AND_ROADMAP.md` session (footnote at that file's line 6: "the file referenced as M18_1_INTEGRATION_MATRIX.md does not exist in this repo — confirmed by listing"). This audit reconciles against `M18_LIVE_INTEGRATION_REPORT.md` instead, per that established substitution.

| Area | BEFORE (M18) | CURRENT (re-verified now) | RESOLVED? | EVIDENCE | REMAINING GAP |
|---|---|---|---|---|---|
| Dashboard | 100% mock (`M18_LIVE_INTEGRATION_REPORT.md:48`) | KPI cards + 2 charts + Findings widget now real (M20.1/M20.3) | **PARTIAL** | `dashboard/page.tsx:16` (mock findings import for Maintenance Ops Snapshot still present), `:31` (real findings API import), `:218` (`RealFindingsPanel`) | Maintenance Operations Snapshot section and other KPI rows still mock/"Illustrative Data" per M20.1's own labeling |
| Findings (general) | Did not exist at all (backend); disconnected mock on dashboard (`M20_AUDIT_AND_ROADMAP.md` §1.3) | Real `Finding`/`FindingDisposition` model, API, dashboard widget, and detail route (M20.2-M20.4) | **RESOLVED** for aircraft + drone-linked findings reachable via the model | `backend/app/models/finding.py`, `backend/app/api/v1/findings.py:19-109`, `dashboard/page.tsx:218-335`, `frontend/app/(app)/findings/[id]/page.tsx:157-167` | No general Finding is ever *created* from the drone side of the app (see §3) — only from the aircraft detail page (`fad9ae1` scope) or presumably an API client directly |
| Purchase-order detail | Live (`M18...md:1.4` table lists `purchase-orders` page as live) | Not re-verified this session (out of drone-focused scope) | **NOT VERIFIED** (not re-checked) | — | N/A this audit |
| Dashboard/control-center | Control tower = mock, no backend equiv (`M18...md:57`) | Not re-checked this session | **NOT VERIFIED** | — | Carry forward |
| Work orders | Live list/detail, legacy checklist mock sub-panel (`M18...md:44`) | Not re-checked this session | **NOT VERIFIED** | — | Carry forward |
| Inspections | Dual (mock legacy UI + live API) (`M18...md:45`) | Not re-checked this session | **NOT VERIFIED** | — | Carry forward |
| Parts | List live, detail mock (`M18...md:47`) | Not re-checked this session | **NOT VERIFIED** | — | Carry forward |
| Technicians | Dual, real implemented, code-verified only, not browser-proven (`M18...md:41`) | Not re-checked this session | **NOT VERIFIED** | — | Carry forward |
| AOG recovery | Not explicitly classified in M18 table | Not checked this or prior session | **NOT VERIFIED** | — | Unknown state |
| Drone list/detail, flights, lifecycle, maintenance | Already live, "reference pattern" (`M18...md:34`) | Re-confirmed live this session (§3 below) | **CONFIRMED STILL LIVE** | `frontend/app/(app)/drones/page.tsx`, `.../drones/[id]/page.tsx`, `backend/app/api/v1/drones.py` | Drone detail page has **no Findings panel** (see §3) — a real gap this audit newly surfaces, not previously flagged in M18/M20 roadmap docs |

---

## 3. Drone product layer-by-layer audit

Read `frontend/app/(app)/drones/page.tsx` (195 lines) and `frontend/app/(app)/drones/[id]/page.tsx` (571 lines) in full, plus `backend/app/api/v1/drones.py` routes.

| Layer | Classification | Evidence |
|---|---|---|
| Drone Fleet (list) | **LIVE** | `drones/page.tsx:42-52` calls `dronesApi.listDrones(accessToken)`; no mock import in file |
| Drone Detail (identity) | **LIVE** | `drones/[id]/page.tsx:132` `dronesApi.getDrone` |
| Flights | **LIVE** | `drones/[id]/page.tsx:113-121` (`listFlights`, paginated), `:184-212` (`recordFlight`); backend `drones.py:199-254` |
| Utilization | **LIVE** | `drones/[id]/page.tsx:135,198` `getUtilization`; backend `drones.py:256-266` |
| Batteries | **LIVE** | `drones/[id]/page.tsx:133,151` `listBatteries`; lifecycle history `getBatteryHistory` (`:151`); backend `drones.py:114-165` |
| Components | **LIVE** | `drones/[id]/page.tsx:134,152` `listComponents`/`getComponentHistory`; backend `drones.py:166-197` |
| Maintenance (asset/battery/component) | **LIVE** | `drones/[id]/page.tsx:81-104` (`getMaintenanceDue`, `getBatteryMaintenanceDue`, `getComponentMaintenanceDue`), write actions `createMaintenanceRequirement`/`recordMaintenanceAccomplishment` at `:310-332, 389-411, 536-554`; backend `drones.py:366-442+` |
| Work Orders | **NOT IMPLEMENTED (on drone detail page)** | No `work_order`/`workOrder` reference anywhere in `drones/[id]/page.tsx`; drone-linked work orders would need to be viewed elsewhere (e.g. via `WorkOrder.asset_id`, not confirmed reachable from this page) |
| Inspections | **NOT IMPLEMENTED (on drone detail page)** | No inspection reference in either drone file |
| Evidence | **NOT IMPLEMENTED (on drone detail page)** | No evidence reference in either drone file |
| Compliance | **NOT IMPLEMENTED (on drone detail page)** | No compliance reference; drone status badges (`ACTIVE`/`GROUNDED`) are asset-status only, not a compliance assessment |
| Readiness (Deployment Readiness) | **LIVE** | `drones/[id]/page.tsx:136,244-257` renders `readiness.status` + `readiness.blockers[]` from `getDeploymentReadiness`; backend `drones.py:268-288` |
| Findings | **NOT IMPLEMENTED (on drone detail page)** | Confirmed by full read of `drones/[id]/page.tsx` — no `finding`/`Finding` string anywhere in the file. The M20.2-M20.4 general Finding model *does* support `asset_id` (drone) linkage end-to-end (`frontend/app/(app)/findings/[id]/page.tsx:166-167` renders a "View Drone" link when `finding.asset_id` is set, and `backend/app/models/finding.py`'s dual aircraft/asset FK pattern per `M20_2_REPORT.md:35`), but nothing on the drone side ever *creates* or *lists* a Finding — the only creation UI shipped in M20.2 is `frontend/app/(app)/aircraft/[id]/page.tsx`'s `AircraftFindingsPanel` (per `M20_2_REPORT.md:29-30`). A drone-linked Finding is reachable only if created directly against the API (e.g. by curl or a future UI), then it renders correctly on the dashboard/detail route — but no in-product path exists to create one from a drone screen. |

**This is a genuine, newly-surfaced gap**: the Finding model is drone-capable end-to-end at the data/API/detail-route layer, but the *product* (drone list/detail UI) has zero Finding creation or listing surface — asymmetric with the aircraft side, which got a full panel in M20.2.

---

## 4. Frontend mock-data scan

`frontend/lib/mock/` contains 33 files (`ls` output: `aircraft.ts, assessments.ts, audit.ts, cannibalization.ts, checklists.ts, components.ts, defects.ts, deferredItems.ts, documentLibrary.ts, engines.ts, evidence.ts, evidenceRecords.ts, finance.ts, findings.ts, inspectorReviews.ts, integrations.ts, kleene.ts, maintenance.ts, maintenanceAccomplishments.ts, maintenanceProgram.ts, maintenanceProjects.ts, maintenanceTasks.ts, organizations.ts, partTraceability.ts, parts.ts, procurement.ts, regulations.ts, reports.ts, roles.ts, search.ts, technicians.ts, types.ts, workOrders.ts`, plus `ai/*`).

`grep -rn "mock/findings"` across `frontend` shows `lib/mock/findings.ts` is still imported live by 8 files:
- `frontend/app/(app)/compliance/page.tsx:16`
- `frontend/app/(app)/compliance/pre-audit/page.tsx:9`
- `frontend/app/(app)/dashboard/page.tsx:16` (self-labeled "Illustrative Data" per M20.3's commit message, confined to the Maintenance Operations Snapshot section)
- `frontend/app/(app)/maintenance/inspections/page.tsx:15`
- `frontend/app/(app)/maintenance/inspections/[id]/page.tsx:18`
- `frontend/app/(app)/maintenance/operations/page.tsx:7`
- `frontend/app/(app)/maintenance/work-orders/[id]/page.tsx:11`
- `frontend/app/(app)/pilot/page.tsx:10`

Classification (drone/fleet-operational-state relevance only, not exhaustive of all 33 mock files):
- `lib/mock/findings.ts` on compliance, inspections, work-orders, pilot pages: **PRODUCTION MOCK** — represents operational checklist-exception state as fake data on screens not explicitly labeled illustrative (only the dashboard usage is self-labeled).
- `lib/mock/findings.ts` on dashboard: **DEMO-STATIC** (self-labeled "Illustrative Data" per M20.1/M20.3 commit messages — not re-verified character-by-character that every one of these dashboard sections carries a visible label; only the commit messages' own claim was checked, not a full accessibility/DOM read of every label).
- `lib/mock/partTraceability.ts`: **PRODUCTION MOCK** per prior M20 audit (§1.4 of `M20_AUDIT_AND_ROADMAP.md`) — not re-verified this session, carried forward.
- `lib/mock/maintenanceProgram.ts`, `lib/mock/evidence.ts`/`evidenceRecords.ts`: **PRODUCTION MOCK** per M18 (§1.4 table rows "Maintenance program," "Evidence list/detail" = mock) — not re-verified this session, carried forward as prior findings, not re-confirmed by fresh reads.

No file in `frontend/lib/mock/` was found this session representing drone-specific operational state (drone counts/flights/batteries/components/readiness) as fake data — the drone screens are fully live per §3, so there is no drone-side production mock to flag.

---

## 5. API contract audit

- `frontend/lib/api/findings.ts` (per `fad9ae1`/`8c9dff1` diffs, 82+10 lines) vs. `backend/app/schemas/finding.py` (83 lines, per `fad9ae1` diffstat): not diffed field-by-field this session against the live schema file content — **NOT VERIFIED** at the granular-field level. The route-level contract (paths, RBAC-gated read/write split) is confirmed matching between `findings.ts`'s consumers (`dashboard/page.tsx`, `findings/[id]/page.tsx`) and `backend/app/api/v1/findings.py`'s actual route signatures (§2 above), and `frontend/tests/finding-detail.test.ts:67-92` explicitly tests that a 404 and a 500 normalize to distinct error kinds — i.e. error-shape handling is unit-tested, not merely assumed.
- `frontend/lib/api/drones.ts` was not opened this session (large surface, 15+ backend endpoints) — pagination (`FlightListResponse` with `total`/`offset`/`limit`, confirmed used correctly at `drones/[id]/page.tsx:57-58,113-121`) appears correctly modeled from the consumer side, but the schema file itself (`backend/app/schemas/*` for drones) was not opened to verify field-for-field. **NOT VERIFIED** at the schema level.
- No mismatches were found or invented; the honest state is that route/shape *consistency was inferred from consumer code compiling/matching usage patterns*, not from a side-by-side schema diff for every field. This is weaker evidence than a full contract test and is reported as such rather than claimed as COMPLETE.

---

## 6. Tenant isolation audit

Read `backend/app/api/v1/findings.py` and `backend/app/api/v1/drones.py` route signatures directly:

- Every `findings.py` route (`create_finding` at `:20-33`, `list_findings` at `:50-60`, `get_finding` at `:70-76`, `add_disposition` at `:82-89`, `close_finding` at `:103-109`) declares `current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE|READ))` and passes `organization_id=current_user.organization_id` into the service layer — never a client-supplied `organization_id` field. `findings.py:30` contains an explicit code comment: `# organization_id always comes from the authenticated user, never the request body.`
- Every `drones.py` route inspected (`list_drones:55-59`, `create_drone:64-71`, `get_drone:83-89`, `update_drone:95-103`, `list_batteries:115-121`, `attach_battery:127-135`, `update_battery:148-156`, `list_components:167-173`, `attach_component:179-187`, `list_flights:200-209`, `get_flight:224-230`, `record_flight:236-244`, `get_utilization:257-263`, `get_deployment_readiness:269-275`, `get_battery:291-294`) follows the identical `Depends(require_permission(Permission.DRONE_READ|WRITE))` + `organization_id=current_user.organization_id` pattern.

**Verdict: COMPLETE** for the two routers inspected — organization_id is always server-derived, never client-controlled, at every route read. Other routers (work_orders.py, inspections.py, evidence.py, etc.) were **not** re-read this session; carrying forward M18's own caveat (`M18_LIVE_INTEGRATION_REPORT.md:132`: "no reason from the code read to suspect a general problem... but that is a code-level impression, not something re-verified per-endpoint").

---

## 7. Deployed API audit

Compared local route definitions against the live `/openapi.json`:
- `findings`: all 4 local routes present in deployed openapi (`§1`).
- `drones`: all local routes checked present in deployed openapi (`§1`), including newer sub-resources (`maintenance-due`, `maintenance-requirements/{id}/applicability|accomplishments`, `lifecycle-history`).
- No drift found in either router. Full route-set diff across *all* routers (not just findings/drones) was not performed — **NOT VERIFIED** beyond these two routers, consistent with the task's own scoping to a drone/findings-focused audit.

---

## 8. Migration audit

- `backend/alembic/versions/0036_finding_disposition.py:24-25`: `revision = "0036"`, `down_revision = "0035"` — correctly chained, single head, additive only (docstring: "This is additive only: no existing table is altered"; `upgrade()` body creates exactly `findings` and `finding_dispositions`).
- M20_2_REPORT.md's own claim ("alembic upgrade head → downgrade -1 → upgrade head all ran clean against local Postgres") was **not independently re-run** this session (read-only audit, no destructive/mutating commands permitted) — trusted as a prior first-party report, not re-verified.
- **Deployed staging DB schema state**: **NOT VERIFIED, and cannot be, without DB credentials this audit is not authorized to use.** The public health/ready endpoints (`§1`) confirm the app process is healthy and presumably able to query its configured DB (a `/health/ready` typically implies a DB round-trip succeeded), but this does not by itself prove migration `0036` specifically has been applied on the deployed database versus some earlier revision — that would require either DB introspection credentials or exercising an authenticated `/findings` API call against staging, neither of which this audit is authorized to do. Stating this limitation honestly per the task's own instruction rather than skipping it.

---

## 9. Deployment health

Re-confirmed via quick GET requests (`§1`): frontend `200`, backend `/api/v1/health` `200`, `/api/v1/health/ready` `200`, `/openapi.json` `200`, `/findings/test-id` `200` (dynamic route resolves without a hard 404/500 shell error, though the specific finding obviously doesn't exist — page-shell reachability only, not data-content verification, since that would require auth).

---

## 10. Authenticated verification status

**AUTHENTICATED BROWSER VERIFICATION = NOT VERIFIED — no authorized credentials available.** No login was attempted against staging with any password (guessed, fabricated, or otherwise). All checks in this report are either (a) local static/git analysis, (b) public unauthenticated HTTP GETs, or (c) reading prior sessions' own first-party test-run claims without re-executing them. No claim in this report should be read as "logged in and clicked through it."

---

## 11. M18 mock-data findings — see §4 above (merged per instructions' overlap with the mock-scan section).

---

## 12. M20 completion matrix

| Area | M20 Target | Current State | Evidence | Verified? | Remaining Gap |
|---|---|---|---|---|---|
| Dashboard real KPIs | Replace mock KPI tiles with live counts | Done for aircraft/drone/work-order/deferred-item counts | `100959f` diff, `dashboard/page.tsx` current imports | COMPLETE (code-read); NOT VERIFIED (no browser run this session) | Other dashboard sections remain mock, self-labeled |
| Dashboard real charts | 2 CSS bar charts from live data | Fleet-status + work-order-status bars added | `100959f` diffstat (`globals.css` +71, page +224) | COMPLETE (code-read) | No time-series/workload/life-exposure charts (out of M20 scope, noted in `M20_AUDIT_AND_ROADMAP.md` roadmap item 8) |
| Finding backend model | Tenant-scoped Finding+Disposition | `Finding`/`FindingDisposition`, migration 0036 | `fad9ae1` diff, `backend/app/models/finding.py`, migration file read | COMPLETE (code-read); migration up/down/up NOT independently re-run this session | Deployed staging DB schema state not directly verifiable (§8) |
| Finding API | CRUD + disposition/close, RBAC | `/findings` router, 4 routes, all deployed | `findings.py:19-109`, `§1`/`§7` openapi match | COMPLETE | None found |
| Finding RBAC/audit | Reuse INSPECTION_READ/WRITE, audit events | Confirmed reused; audit events per `finding_service.py` per `M20_2_REPORT.md:60` (not independently re-read this session) | `findings.py` route decorators (§6) | COMPLETE for RBAC (code-read); audit-event write path NOT re-verified this session (trusted from M20_2_REPORT) | — |
| Dashboard findings widget | Replace mock with real Finding data | `RealFindingsPanel` live | `dashboard/page.tsx:31,218,335` | COMPLETE (code-read) | Old mock import (`:16`) still present for unrelated section |
| Finding detail route | Canonical `/findings/[id]` | Exists, handles aircraft- and drone-linked findings | `findings/[id]/page.tsx:157-167` | COMPLETE (code-read); unit-tested, not browser-tested | No browser verification (§10) |
| Finding-to-asset navigation | Link from finding to its aircraft/drone | "View Aircraft"/"View Drone" links present | `findings/[id]/page.tsx:157-167` | COMPLETE (code-read) | None found |
| Tenant isolation for findings | organization_id server-derived only | Confirmed at every route | `findings.py:30` comment + every route (§6) | COMPLETE (code-read) | Cross-org 404 behavior claimed by `fad9ae1`'s integration tests, not re-run this session |
| Frontend tests | Coverage for new UI | `frontend/tests/finding-detail.test.ts`, 6 tests | File read, `§2` M20.4 section | COMPLETE (existence + content read); NOT VERIFIED (tests not re-run this session — read-only audit) | No component-level test for `AircraftFindingsPanel` (`M20_2_REPORT.md:82`) |
| Backend tests | Coverage for new model/API | `test_finding_lifecycle.py` (7), `test_finding_api.py` (6) = 13 tests, reported 1010/1010 full suite passing | `fad9ae1` diffstat, `M20_2_REPORT.md:66-67` | COMPLETE (existence read); NOT VERIFIED (not re-run this session) | — |
| Migration correctness | Reversible, additive, chained | `0036` revises `0035`, additive-only body | Migration file read (§8) | COMPLETE (code-read); up/down/up execution NOT VERIFIED this session | Deployed DB actual schema state NOT VERIFIED (no DB credentials, §8) |
| Drone-side Finding creation/listing UI | *(not an original M20 target, newly surfaced)* | Does not exist | §3 full read of `drones/[id]/page.tsx` (no `finding` reference) | NOT COMPLETE | This is the asymmetry driving the recommendation below |

---

## 13. Recommended next vertical slice (exactly one)

**M20.5 — Add a Findings panel to the drone detail page (`frontend/app/(app)/drones/[id]/page.tsx`), mirroring the existing `AircraftFindingsPanel` pattern from `frontend/app/(app)/aircraft/[id]/page.tsx` (M20.2).**

Rationale: this audit's own drone-layer walkthrough (§3) found every other drone-detail layer (fleet, identity, flights, utilization, batteries, components, maintenance, readiness) already LIVE, but Findings — the exact capability M20.2-M20.4 just built out generically, with a backend that already supports `asset_id` (drone) linkage end-to-end (`findings/[id]/page.tsx:166-167`'s "View Drone" link proves the read/render path already works for drone-linked findings) — has **zero creation or listing surface on the drone side**. This is a smaller, better-founded gap than re-opening the stale M18/M20 roadmap items (navigation regrouping, component genealogy, role-based dashboards), because the backend, RBAC, audit, and even the detail-route rendering are already proven; only the creation/listing UI on one page is missing, following an established, working pattern rather than inventing a new one.

Definition of Done:
- Backend: no new model/route/permission — reuse `POST /findings`, `GET /findings?asset_id=`, `POST /findings/{id}/dispositions`, `POST /findings/{id}/close` exactly as `AircraftFindingsPanel` does, substituting `asset_id` for `aircraft_id`.
- Frontend: add a `DroneFindingsPanel` component to `drones/[id]/page.tsx`, gated the same way (`RealDataPanel`, `useSession`, live-only, no DEMO-mode branch needed since the whole page is already REAL-only), listing findings filtered by `asset_id`, supporting raise/disposition/close.
- Tests: at minimum, a `frontend/tests/*.test.ts` covering the panel's API-client usage (mirroring the pattern of `finding-detail.test.ts`), and confirm the existing backend integration tests (`test_finding_api.py`) already cover `asset_id`-filtered list (verify, don't assume — read the test file before claiming coverage).
- Browser verification: local dev server, create a drone, raise a finding against it via the new panel, confirm it appears both on the drone detail page and via the dashboard `RealFindingsPanel` / `/findings/[id]` route (closing the loop this audit found half-open) — logged as PROVEN only if actually driven, not inferred.
- Explicitly out of scope: no navigation restructure, no new permission, no DEMO-mode branch, no touching the aircraft-side panel.

---

## 14–15. Evidence index / limitations summary

All file:line citations above are drawn from direct reads performed this session:
- `backend/app/api/v1/findings.py`, `backend/app/api/v1/drones.py`, `backend/alembic/versions/0036_finding_disposition.py`
- `frontend/app/(app)/drones/page.tsx`, `frontend/app/(app)/drones/[id]/page.tsx`, `frontend/app/(app)/dashboard/page.tsx` (grep-located lines), `frontend/app/(app)/findings/[id]/page.tsx` (grep-located lines), `frontend/tests/finding-detail.test.ts`
- `git show --stat` for `100959f`, `fad9ae1`, `8c9dff1`, `fce85bf`
- `M20_AUDIT_AND_ROADMAP.md`, `M20_2_REPORT.md`, `M18_LIVE_INTEGRATION_REPORT.md` (read in full or substantially)
- Public GETs: `aerocomply.vercel.app`, `aerocomply-backend-staging.onrender.com/api/v1/health`, `/health/ready`, `/openapi.json`, `/findings/test-id`

Honest limitations (explicitly not glossed over): no authenticated browser session was run (§10); no test suite was re-executed this session (all pass/fail counts are trusted from prior first-party reports, not reproduced); no deployed-DB schema introspection was performed or possible without credentials (§8); the API contract audit (§5) is route/usage-level, not a full field-by-field schema diff; only two backend routers (`findings`, `drones`) received a full tenant-isolation line-by-line read — other routers' isolation is carried forward from M18's own caveat, not re-checked.
