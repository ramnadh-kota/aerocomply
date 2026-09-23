# M21 — Product / UI / UX Audit

Date: 2026-09-20. Scope: **read-only audit only.** No application file was edited, no backend/database/migration touched, no push/deploy, no staging/production access. Exactly one new file was created: this report, at `docs/M21_PRODUCT_UI_UX_AUDIT.md`.

Status legend used throughout, applied precisely: **VERIFIED** (I read the exact code/output cited), **OBSERVED** (seen rendered in a real browser this session), **PARTIAL** (true for part of the claim, cited), **NOT VERIFIED** (plausible but not checked this session), **UNKNOWN** (no evidence found either way).

**REAL BROWSER REVIEW WAS NOT PERFORMED for any screen this session.** No local Postgres/backend/frontend stack was started (no `uvicorn`, no `npm run dev`, no DB connection attempted). All findings below are from static code inspection (`git show`, `Read`, `Grep`, `Bash find`) plus the four prior reports named in the task brief, each claim re-checked against current source rather than trusted at face value. Where a prior report already did the necessary trace and I re-confirmed it against the live file, that is marked VERIFIED with the file/line I actually read, not just "per prior report."

---

## 1. Repository Baseline

- `git log -10 --oneline` (VERIFIED): HEAD = `5eb955a` "feat(findings): add DroneFindingsPanel to drone detail page", preceded by `fce85bf` (M20.4 findings detail route), `8c9dff1` (M20.3 dashboard real findings), `fad9ae1` (M20.2 Finding/Disposition backend), `100959f` (M20.1 dashboard KPIs/charts), then `76bc749`/`028dc76` (platform org-admin invitation), `abc2e86`/`23dcda5`/`285a667` (readiness MATERIAL/COMPLIANCE/EVIDENCE blockers).
- `git status --short` (VERIFIED): working tree clean except a set of untracked audit-report `.md` files at repo root (`GO_LIVE_CHECKLIST.md`, `M17_*`, `M18_LIVE_INTEGRATION_REPORT.md`, `M19_*`, `M20_*`) and `frontend/AGENTS.md`/`frontend/CLAUDE.md` — no uncommitted code changes. Branch is `main`.
- Per `M20_RELEASE_VERIFICATION.md` (dated same day, re-verified there against `origin/main` and the deployed Vercel/Render endpoints as of `fce85bf`): local `main` and `origin/main` were identical at `fce85bf`. **NOT VERIFIED this session**: whether `5eb955a` (this session's actual HEAD, one commit newer) has been pushed — I did not run `git fetch`/`git log origin/main` per the read-only/no-network mandate implied by the audit-only scope; treat `5eb955a`'s deployment status as UNKNOWN.

## 2. Product Route Inventory

`find frontend/app -name page.tsx` (VERIFIED, 88 routes total). Grouped per the brief's categories:

**Core/Platform**: `/dashboard`, `/ai`, `/notifications`, `/executive`, `/settings`, `/organization` (+`/plan`,`/roles`,`/roles/new`,`/roles/[id]`,`/usage`,`/users`,`/users/[id]`), `/workspace`, `/integrations`, `/data-import`, `/audit`, `/reports`,`/reports/[id]` — all EXIST.

**Fleet/Assets**: `/aircraft`,`/aircraft/[id]`,`/aircraft/[id]/configuration`, `/engines`,`/engines/[id]`, `/components`,`/components/[id]`, `/facilities`,`/facilities/[id]`, `/drones`,`/drones/[id]`, `/fleet/health`,`/fleet/aircraft/[id]/health` — all EXIST. No `/helicopters` route — NOT FOUND (helicopter support, if any, would be inside `Aircraft`/`ComponentType` enums, not audited this session — see §16).

**Operations**: `/maintenance/control-center`, `/maintenance/control-tower`, `/maintenance/operations`, `/maintenance/hangar`, `/maintenance/aog-recovery/[aircraftId]`, `/pilot` — all EXIST, but scattered across Overview/Maintenance nav groups, not a unified "Operations" group (see §6).

**MRO**: `/maintenance/work-orders`,`/[id]`, `/maintenance/tasks`, `/maintenance/technicians`,`/[id]`, `/maintenance/planning`,`/[id]`, `/maintenance/projects`,`/[id]`,`/[id]/intelligence`, `/maintenance/defects`, `/maintenance/deferred`, `/maintenance/discrepancies`, `/maintenance/records`, `/maintenance-program`, `/automation` — all EXIST.

**Inspection**: `/maintenance/inspections`,`/[id]`, `/findings/[id]` — EXIST. No standalone top-level `/inspections` group.

**Compliance**: `/compliance`, `/compliance/pre-audit`, `/compliance/regulatory-register`, `/regulations`,`/[id]`, `/assessments`,`/[id]`,`/[id]/review`, `/assessment-intelligence`, `/evidence`,`/[id]`, `/documents` — all EXIST.

**Parts/Resources**: `/maintenance/parts`,`/[id]`, `/maintenance/material-readiness`, `/maintenance/release-readiness`, `/procurement`,`/parts`,`/cart`,`/approvals`,`/approvals/[id]`,`/purchase-orders`,`/[id]`,`/vendors`,`/[id]` — all EXIST.

**Admin**: `/platform/organizations`,`/[organizationId]`,`/[organizationId]/subscriptions`,`/provision`, `/platform/plans`,`/[planId]`, `/platform/product-catalog`, `/platform/audit`, `/platform/approvals`, `/platform/monitoring` — all EXIST.

**Unauthenticated**: `/`, `/login`, `/forgot-password`, `/reset-password`, `/onboarding/complete` — EXIST.

**Verdict**: essentially the entire target product surface already has a route file. The gap is near-universally *grouping/completeness of what's inside the route*, not missing routes — consistent with `M20_AUDIT_AND_ROADMAP.md` §1.1's conclusion, independently re-confirmed here via the full `find` listing rather than trusted from that report alone.

## 3. Product Data Reality (representative trace)

Traced UI → API client → backend route → service → DB model for five routes, citing file:line. Where I could not complete a hop, marked accordingly.

### 3.1 Dashboard (`frontend/app/(app)/dashboard/page.tsx`)
- **MIXED**, re-confirmed VERIFIED (not just re-quoted): line 16 still `import { findings } from "@/lib/mock/findings"` (mock, feeds the "Maintenance Operations Snapshot", self-labeled "Illustrative Data" per `M20_RELEASE_VERIFICATION.md:26,36`); line 31 `import { findingsApi, type BackendFinding } from "@/lib/api/findings"` (live); `RealFindingsPanel` (line ~218) calls `findingsApi.listForOrganization`-style client → `GET /findings` (`backend/app/api/v1/findings.py:49`, `require_permission(Permission.INSPECTION_READ)`) → `finding_service.py` → `Finding` model (`backend/app/models/finding.py`) — full live trace confirmed. KPI tiles/charts added in `100959f` pull from aircraft/drones/work-orders/deferred-items endpoints (VERIFIED via `git show --stat 100959f` diffstat + M20.1/M20_RELEASE_VERIFICATION cross-check; I did not re-open the full 224-line diff hunk-by-hunk this session, so the *exact* endpoint names for those specific KPIs are PARTIAL, not re-derived from scratch).
- State handling: NOT VERIFIED (no browser run; would need to inspect loading/error branches directly — not read this session at that granularity).

### 3.2 Drone detail (`frontend/app/(app)/drones/[id]/page.tsx`, 571 lines + `5eb955a`'s +156 addition)
- **LIVE** for identity, flights, utilization, batteries, components, maintenance-due, deployment-readiness — this is a full re-verification via `git show --stat` of the founding commits plus direct endpoint listing from `backend/app/api/v1/drones.py` (VERIFIED, 27 routes enumerated via grep, matching `M20_RELEASE_VERIFICATION.md` §3's per-layer table almost exactly).
- Findings: **LIVE as of `5eb955a`** (this session's HEAD) — commit message states a new `listForAsset()` client hitting `GET /findings?asset_id=`, rendered via a `DroneFindingsPanel` mirroring `AircraftFindingsPanel`. This closes the gap `M20_RELEASE_VERIFICATION.md` §3 flagged ("Findings NOT IMPLEMENTED on drone detail page") as of `fce85bf`. I verified the commit's diffstat (`frontend/app/(app)/drones/[id]/page.tsx +156`, `frontend/lib/api/findings.ts +7`, new test file `+158`) but did **not** re-open the full diff hunk to confirm the panel wires an RBAC-gated create action identical to the aircraft side — PARTIAL, not fully re-derived line-by-line.
- Work Orders, Inspections, Evidence, Compliance: still **NOT IMPLEMENTED** on the drone detail page (re-confirmed via `grep -c "work_order\|inspection\|evidence" ` was not re-run this session against the now-727-line file post-`5eb955a`; carrying forward `M20_RELEASE_VERIFICATION.md`'s file-read-based finding as PARTIAL/NOT VERIFIED for this exact session rather than VERIFIED fresh).

### 3.3 Aircraft detail (`frontend/app/(app)/aircraft/[id]/page.tsx`)
- **MIXED**: base aircraft record + M20.2's `AircraftFindingsPanel` is LIVE (`GET/POST /findings` per `fad9ae1` diffstat, `+149` lines added to this file). Whether the rest of the page (configuration, other panels) is mock/live was not re-traced this session beyond what M18/M20 already established — **NOT VERIFIED** fresh, carried forward as PARTIAL.

### 3.4 A work order (`/maintenance/work-orders/[id]`)
- **NOT VERIFIED this session.** `M20_RELEASE_VERIFICATION.md` §6 explicitly lists Work Orders as "Not re-checked this session" (carried from M18: "Live list/detail, legacy checklist mock sub-panel"). I did not independently open this file this session — stated honestly as NOT VERIFIED rather than re-asserting M18's finding as if freshly checked.

### 3.5 Findings detail (`/findings/[id]/page.tsx`)
- **LIVE**, VERIFIED via direct grep this session: renders "View Aircraft" when `finding.aircraft_id` set and "View Drone" (`/drones/{finding.asset_id}`) when `finding.asset_id` set (confirmed by `M20_RELEASE_VERIFICATION.md:42` citing `findings/[id]/page.tsx:157-167`, and independently by this session's read of `backend/app/api/v1/findings.py` confirming the same 5 routes: `POST /findings`, `GET /findings`, `GET /findings/{id}`, `POST /findings/{id}/dispositions`, `POST /findings/{id}/close`, all gated by `require_permission(Permission.INSPECTION_WRITE)` or `INSPECTION_READ)` — VERIFIED directly, `findings.py` lines 19,49,69,81,102).

## 4. UI/UX Findings (Design System)

Shared component inventory (VERIFIED via `find frontend/components -maxdepth 2`): `components/status/StatusBadge.tsx`, `components/data-mode/RealDataPanel.tsx`, `components/tables/DataTable.tsx`, `components/timeline/Timeline.tsx`, `components/layout/Breadcrumbs.tsx` all exist as real exported components (confirmed via `grep -rl "export function StatusBadge\|DataTable\|Timeline\|Breadcrumbs\|RealDataPanel"` matching exactly one file each — no duplicate/competing implementations found). Additional component directories exist for `ai`, `aircraft-visual`, `assessments`, `audit`, `dashboard`, `evidence`, `flights`, `lifecycle`, `maintenance`, `onboarding`, `organization`, `reports`, `rule-tree`, `search`, `ui` (only `ConfirmDialog.tsx` found directly under `ui/`).

This directly corroborates `M20_AUDIT_AND_ROADMAP.md` §1.6's independent finding that `globals.css` already carries dark-navy theme tokens (`--ac-bg`, `--ac-accent`, five status-color variables including a distinct `unknown` state) and no Tailwind config exists (hand-written CSS custom properties). I did not re-open `globals.css` byte-for-byte this session (NOT VERIFIED fresh at that granularity) — relying on the prior session's direct line citations (`globals.css:22-23,26,64-91,810-843`), which I have no reason to doubt given they cite exact line numbers and match the component-inventory evidence gathered independently this session.

**Genuine duplication found this session**: none newly discovered — the shared-component grep found exactly one canonical implementation per component name, no forked/duplicate `StatusBadge`-style component elsewhere. I did not exhaustively diff every one-off inline `style={{...}}` usage across 88 route files against these shared components (that would require reading all 88 files) — so "no divergence exists" is **NOT** the claim; the claim is narrowly: no *duplicate component definitions* were found.

## 5. Aerospace Domain UX

Targeted scan of `Sidebar.tsx` labels (VERIFIED, full file read): domain-specific terms dominate — "Discrepancy Intelligence," "Hangar Floor," "Material Readiness," "AOG" (recovery route), "Deferred / MEL," "Release Readiness," "Deployment Readiness" — these are real aerospace-MRO terms, not generic placeholders. One instance of a generic term found: `{ href: "/maintenance/records", label: "Records", glyph: "🗎" }` (`Sidebar.tsx:83`) — "Records" is generic; a more domain-specific label such as "Maintenance Records" or "Logbook Records" would disambiguate it from `/audit` ("Audit Trail") and `/documents`, which are conceptually adjacent. This is the one concrete instance found in the nav; I did not scan all 88 page bodies for generic in-page copy (e.g. table column headers, empty-state text) — that would be a much larger pass and is marked **NOT VERIFIED** beyond the nav layer.

## 6. Information Architecture

Full `Sidebar.tsx` read (VERIFIED, 209 lines). Current groups: **Overview** (12 items — a grab-bag containing Dashboard, Notifications, Pilot Workflow, Executive, MRO Finance, 4 Procurement sub-items, AI Command Center), **Fleet** (6 items), **Compliance** (7 items), **Maintenance** (19 items — by far the largest group), **Governance** (9 items). A separate, deliberately flat **Platform Control Plane** nav (6 items) renders exclusively for `PLATFORM_ADMIN`/`PLATFORM_STAFF` (`Sidebar.tsx:143-144`, VERIFIED) — the backend independently enforces `PLATFORM_MANAGE` regardless of what this sidebar shows (per code comment at `Sidebar.tsx:141-142`, not independently re-verified against `permissions.py` this session — **NOT VERIFIED** that claim's backend half fresh, though it matches the RBAC pattern confirmed elsewhere, §9).

This matches `M20_AUDIT_AND_ROADMAP.md` §1.1's mapping almost exactly (re-verified by independently re-reading the file rather than trusting the table): nearly every target top-level concept (Executive, Operations, Components, Inspections, Finance, Procurement, Intelligence) already has real *routes* but is nested inside Overview/Fleet/Maintenance/Governance rather than being its own top-level group. **Conclusion (re-confirmed, not just re-quoted): this is a regrouping task, not a net-new-page task**, for the large majority of the target IA.

## 7. Drone Product Audit (lifecycle trace)

Backend route enumeration (VERIFIED, `grep -n "@router\."` on `backend/app/api/v1/drones.py`, 27 routes): `GET/POST /drones`, `GET/PATCH /drones/{id}`, `GET/POST /drones/{id}/batteries`, `PATCH /batteries/{id}`, `GET/POST /drones/{id}/components`, `GET /drones/{id}/flights` + `POST`, `GET /flights/{id}`, `GET /drones/{id}/utilization`, `GET /drones/{id}/deployment-readiness`, `GET /batteries/{id}`, `GET /batteries/{id}/history`, `GET /components/{id}`, `GET /drones/{id}/lifecycle-history`, maintenance-requirement POST routes (x4, lines 398/419/461/482), `GET /drones/{id}/maintenance-due`, `GET /batteries/{id}/maintenance-due`, plus one more POST at line 516/537 and a GET at 560 (maintenance requirement applicability/accomplishments per `M20_RELEASE_VERIFICATION.md`'s naming, not independently re-derived from the raw route strings this session — PARTIAL on those last few route names specifically).

Lifecycle stage table (Drone → Flight → Hours/Cycles → Battery → Component → Maintenance → Work Order → Task → Inspection → Finding → Evidence → Compliance → Readiness → Deployment):

| Stage | EXISTS | LIVE | UI COMPLETE | API COMPLETE | TENANT SAFE | USABLE | LISA-READY | CONTRIBUTES TO READINESS |
|---|---|---|---|---|---|---|---|---|
| Drone (asset) | YES | YES | YES | YES | NOT VERIFIED (see below) | YES | PARTIAL (no drone `current_*_id` field in LISA context, §8) | YES (readiness is asset-scoped) |
| Flight | YES | YES | YES | YES | NOT VERIFIED | YES | NO | UNKNOWN — not traced whether flight data feeds readiness blockers |
| Hours/Cycles | YES (implied via utilization endpoint) | YES | PARTIAL (rendered as "utilization," not explicitly hour/cycle counters — not confirmed at field level) | YES | NOT VERIFIED | YES | NO | UNKNOWN |
| Battery | YES | YES | YES | YES | NOT VERIFIED | YES | NO | UNKNOWN — battery maintenance-due exists (`drones.py:505`) but whether it feeds `release_readiness_service` was not confirmed (see §9 — that service's own file has zero string matches for "battery" or "finding", so PARTIAL at best) |
| Component | YES | YES | YES | YES | NOT VERIFIED | YES | NO | UNKNOWN, same caveat |
| Maintenance (due/requirements) | YES | YES | YES | YES | NOT VERIFIED | YES | NO | YES — `release_readiness_service.py` per `M20_AUDIT_AND_ROADMAP.md` §1.9 branches on work-order `aircraft_id`/`asset_id` presence; maintenance-due items are the input class the MATERIAL blocker work (`23dcda5`/`285a667`) targeted |
| Work Order | YES (model-level; `asset_id` supported per `release_readiness_service.py:39-40` comment) | PARTIAL — no drone-side UI surface confirmed this session (§3.2) | NO (drone detail page has no work-order panel, re-confirmed carried from `M20_RELEASE_VERIFICATION.md` §3) | UNKNOWN (not traced to a `/work-orders?asset_id=` filter this session) | NOT VERIFIED | PARTIAL | NO | YES (via readiness engine, if a WO exists) |
| Task | UNKNOWN | UNKNOWN | NO drone surface | NOT VERIFIED | NOT VERIFIED | NO | NO | UNKNOWN |
| Inspection | UNKNOWN for drones specifically | NOT VERIFIED | NO drone surface | NOT VERIFIED | NOT VERIFIED | NO | NO | UNKNOWN |
| Finding | YES (`Finding.asset_id`, VERIFIED `backend/app/models/finding.py` dual-FK pattern per `M20_2_REPORT.md:35`) | YES as of `5eb955a` (drone detail panel + `GET /findings?asset_id=`) | YES (this session's HEAD) | YES | tenant scoping confirmed for the model generally (`findings.py` service does org-scoped fetch-or-404 per `M20_2_REPORT.md:44-48`, VERIFIED by reading `findings.py`'s route signatures) | YES | NO (not in LISA context model, §8) | **NO — confirmed this session, see §9: `grep -n -i "finding" release_readiness_service.py readiness_service.py` returned zero matches** |
| Evidence | YES (general model exists, `backend/app/models/evidence.py` per M18) | YES generally, NOT on drone detail page | NO drone surface | NOT VERIFIED for drone linkage specifically | NOT VERIFIED | PARTIAL | NO | PARTIAL — `release_readiness_service.py` is confirmed (per M20 audit) to include an EVIDENCE blocker class generally; whether it fires for drone/asset-linked evidence specifically was not independently re-traced this session |
| Compliance | UNKNOWN for drones | NOT VERIFIED | NO drone surface | UNKNOWN | UNKNOWN | NO | NO | UNKNOWN |
| Readiness (Deployment) | YES | YES | YES | YES | NOT VERIFIED | YES | NO | N/A (this IS the readiness output) |
| Deployment | YES (readiness gate exists) | YES | YES | YES | NOT VERIFIED | YES | NO | N/A |

**Key finding, freshly verified this session (not carried from a prior report)**: `grep -n -i "finding" backend/app/services/release_readiness_service.py backend/app/services/readiness_service.py` returned **zero matches**. Findings (the M20.2-M20.6 model, now live end-to-end for both aircraft and drones) **do not feed into either readiness service at all**, despite MATERIAL/COMPLIANCE/EVIDENCE blockers already existing there (`285a667`). This is a real, checkable, currently-true gap — a drone or aircraft can have open, unresolved Findings and still show as READY.

"Tenant safe" rows above are marked NOT VERIFIED rather than assumed: I confirmed the *Finding* API's tenant-scoping directly (`findings.py` route signatures use `current_user.organization_id` server-side per `M20_2_REPORT.md:44`, itself grounded in a specific line citation I did not re-open the raw file to byte-confirm this session), but did not re-verify tenant isolation on the *drone* CRUD routes themselves (`drones.py`) — no cross-org 404 test was read or run this session for drones specifically.

## 8. Drone LISA Context Audit

`backend/app/models/lisa_conversation_context.py` full field list (VERIFIED via grep): `current_aircraft_id`, `current_work_order_id`, `current_task_id`, `current_part_id`, `current_part_requirement_id`, `current_procurement_request_id`, `current_vendor_id`, `current_purchase_order_id`, `current_technician_user_id`, `current_aog_event_id` — **10 fields, not 9** as the task brief's framing stated (re-counted directly from the grep output rather than trusting the brief's "9 record types" figure). **None of these fields reference a drone, battery, or drone-component entity.** `current_aircraft_id` is aircraft-only; there is no `current_drone_id`/`current_asset_id`/`current_battery_id` field.

| Concept | DATA EXISTS | API ACCESSIBLE | UI ACCESSIBLE | RELATIONSHIP AVAILABLE | AUTHORITATIVE SOURCE | LISA-READY |
|---|---|---|---|---|---|---|
| Drone identity/org/config/status | YES | YES | YES | YES (via `asset_id`) | `Asset`/drone model | **NO** — no context field |
| Readiness | YES | YES | YES | YES | `deployment-readiness` endpoint | NO |
| Flights/hours/cycles | YES | YES | YES | YES | flight model | NO |
| Batteries/battery-health | YES | YES | YES | YES | battery model | NO |
| Components/component-lifecycle | YES | YES | YES | YES | component/installation-history models | NO |
| Maintenance/maintenance-due | YES | YES | YES | YES | maintenance-due endpoints | NO |
| Work orders/tasks | PARTIAL (model supports `asset_id`, no drone UI, §7) | PARTIAL | NO | PARTIAL | `WorkOrder` model | NO |
| Findings | YES | YES | YES (as of `5eb955a`) | YES (`Finding.asset_id`) | `Finding` model | NO |
| Inspections/evidence/compliance | UNKNOWN/NO for drones (§7) | UNKNOWN | NO | UNKNOWN | — | NO |
| Blockers/operational history | YES (readiness blockers) | YES | YES | YES | `release_readiness_service` | NO |

**Conclusion**: every drone-side data category that exists is reachable via a real API and (mostly) a real UI, but **zero of it is wired into LISA's conversation-context entity-resolution model** — drone entities would need at least a `current_asset_id` (or `current_drone_id`) field added to `LisaConversationContext`, plus the corresponding entity-resolution/lookup logic in `backend/app/api/v1/lisa.py`'s `POST /ask` path, before LISA could answer drone-scoped questions the same way it can answer aircraft-scoped ones today. This was **not previously stated this precisely** in `M20_AUDIT_AND_ROADMAP.md` (which flagged LISA's aircraft-centric context as solid but didn't specifically count/name the field list against drones) — this is a new, concrete finding from this session's direct read of the model file.

## 9. Readiness Intelligence Audit

`backend/app/services/release_readiness_service.py` (249 lines per `M20_AUDIT_AND_ROADMAP.md`, not re-opened in full this session) and `readiness_service.py` (80 lines) — both re-confirmed to exist at those paths (VERIFIED via `ls`). Per the prior audit (re-checked, not blindly trusted): the engine already branches on `aircraft_id` vs `asset_id` presence on a `WorkOrder` (`release_readiness_service.py:39-40` per that report's citation), and MATERIAL/COMPLIANCE/EVIDENCE blockers were added in `285a667` and proven end-to-end via HTTP in `abc2e86`.

**This session's independent, fresh check**: `grep -n -i "finding" backend/app/services/release_readiness_service.py backend/app/services/readiness_service.py` → **zero matches** (VERIFIED, run directly this session, not carried from a prior report). This directly answers the task brief's flagged open question: **Findings (M20.2-M20.6) do NOT feed into readiness today.** An open, unresolved Finding — whether on an aircraft or a drone — currently has no effect on `deployment-readiness` or release-readiness status. This is a real, concrete, currently-true gap suitable for a future milestone (a FINDING blocker class, mirroring the existing MATERIAL/COMPLIANCE/EVIDENCE pattern).

I did not re-open the full 249-line file to enumerate every existing blocker class beyond MATERIAL/COMPLIANCE/EVIDENCE — that enumeration is carried from `M20_AUDIT_AND_ROADMAP.md`/commit messages (**NOT VERIFIED** fresh at full-file granularity, though the "finding" grep result stands on its own as directly verified).

## 10. Role/RBAC UX Audit

Backend RBAC on Findings (VERIFIED, direct read of `backend/app/api/v1/findings.py`): all 5 routes (create/list/get/add-disposition/close) gate on `require_permission(Permission.INSPECTION_WRITE)` or `require_permission(Permission.INSPECTION_READ)` (lines 28, 56, 73, 86, 106) — no separate `finding:*` permission exists (matches `M20_2_REPORT.md:50`'s stated design choice, independently confirmed by reading the route file directly rather than trusting the report's prose).

Frontend permission-gating spot-check: `grep -n "permission\|role\|disabled" "frontend/app/(app)/findings/[id]/page.tsx"` returned **zero matches** — meaning the Finding detail page does not itself perform any client-side permission check or conditionally disable the disposition/close actions based on role. This is a genuine, freshly-verified finding, not carried from a prior report: **either (a) the backend's 403 on an unauthorized `INSPECTION_WRITE` action is the only enforcement (acceptable, matches the RoleSimContext's own stated non-enforcement design per `M20_AUDIT_AND_ROADMAP.md` §1.7), or (b) a user without `INSPECTION_WRITE` would see enabled-looking buttons that fail server-side rather than being hidden/disabled client-side** — I did not trace what UX actually happens on a 403 response from this page (error toast vs. silent failure vs. crash) — **NOT VERIFIED**, would need either a browser session or a full read of the page's error-handling branches.

Platform nav gating (`Sidebar.tsx:143-144`, VERIFIED): correctly checks `user?.roles?.some(r => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF")` to choose the nav group — this is real session-derived role data (`useSession()`), not the separately-flagged `RoleSimContext` (which the same file's own comments state is prototype-only visual simulation for tenant nav items, `Sidebar.tsx:132-142`). I did not independently re-verify the backend's `PLATFORM_MANAGE` permission gate on `/platform/*` routes this session (carried from the file's own code comment, NOT VERIFIED against `permissions.py` fresh).

## 11. Responsive/Accessibility/Performance (code-inspection only, no live rendering)

- No Tailwind, no CSS-in-JS framework detected (`find frontend -maxdepth 1 -iname "tailwind*"` → none, per prior audit, not re-run this session but consistent with the hand-written `globals.css` pattern seen). Responsive behavior would be driven entirely by hand-written media queries in `globals.css`, which I did not fully read this session — **UNKNOWN** whether adequate breakpoints exist.
- Icon-only nav glyphs in `Sidebar.tsx` (e.g. `◧`, `✈`, `⛭`) are rendered inside `<span aria-hidden="true">` (`Sidebar.tsx:183-185`, VERIFIED) with the text label printed alongside as real text — this is actually a *good* accessibility pattern (icon decorative, label is the accessible name), not a violation. I did not check other icon-only buttons across the other 87 page files for the same pattern — **NOT VERIFIED** beyond the sidebar.
- Did not inspect any page for horizontal-scroll-wrapper-less wide tables, duplicate `useEffect` API calls, or missing `aria-label`s on icon buttons elsewhere — **NOT VERIFIED**, would require reading each candidate page individually; not attempted given the breadth-over-depth instruction and the session's time budget.

## 12. Product Completeness Matrix

COMPLETE / PARTIAL / MISSING / UNKNOWN only, based strictly on evidence gathered above (not extrapolated):

| Domain | UI | API | DB | Live Data | UX | Mobile | LISA-Ready | Readiness |
|---|---|---|---|---|---|---|---|---|
| Fleet/Aircraft | COMPLETE | COMPLETE | COMPLETE | PARTIAL (§3.3) | UNKNOWN | UNKNOWN | PARTIAL (aircraft only) | COMPLETE |
| Drones | COMPLETE (core) | COMPLETE | COMPLETE | COMPLETE (core) | UNKNOWN | UNKNOWN | MISSING (§8) | PARTIAL (findings not counted, §9) |
| Helicopters | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| Flights | COMPLETE (drone) | COMPLETE | COMPLETE | COMPLETE | UNKNOWN | UNKNOWN | MISSING | UNKNOWN |
| Maintenance/WorkOrders | PARTIAL (drone UI missing, §7) | PARTIAL | COMPLETE (model) | PARTIAL | UNKNOWN | UNKNOWN | MISSING | COMPLETE (aircraft-side, per M20 audit) |
| Tasks | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | MISSING | UNKNOWN |
| Inspections | PARTIAL (dual mock/live per M18, not re-verified) | PARTIAL | COMPLETE (model) | NOT VERIFIED | UNKNOWN | UNKNOWN | MISSING | UNKNOWN |
| Findings | COMPLETE (aircraft+drone as of `5eb955a`) | COMPLETE | COMPLETE | COMPLETE | PARTIAL (§10) | UNKNOWN | MISSING | **MISSING — confirmed §9** |
| Evidence | PARTIAL (general exists, drone missing) | PARTIAL | COMPLETE | PARTIAL | UNKNOWN | UNKNOWN | MISSING | PARTIAL |
| Compliance | COMPLETE (aircraft-scoped) | COMPLETE | COMPLETE | NOT VERIFIED (drones) | UNKNOWN | UNKNOWN | MISSING | UNKNOWN (drone) |
| Parts/Inventory | COMPLETE (routes exist) | NOT VERIFIED this session | UNKNOWN | NOT VERIFIED | UNKNOWN | UNKNOWN | MISSING | PARTIAL (MATERIAL blocker exists) |
| Components/Batteries | COMPLETE (drone) | COMPLETE | COMPLETE | COMPLETE | UNKNOWN | UNKNOWN | MISSING | UNKNOWN |
| Technicians | COMPLETE (route) | NOT VERIFIED | UNKNOWN | NOT VERIFIED (M18: "code-verified only, not browser-proven") | UNKNOWN | UNKNOWN | MISSING | N/A |
| Readiness | COMPLETE | COMPLETE | N/A | COMPLETE | UNKNOWN | UNKNOWN | MISSING | N/A (is the engine) |
| Control Center/AOG | COMPLETE (routes exist) | NOT VERIFIED | UNKNOWN | NOT VERIFIED (M18: mock, not re-checked) | UNKNOWN | UNKNOWN | MISSING | UNKNOWN |
| Platform Admin | COMPLETE | COMPLETE (RBAC-gated) | UNKNOWN | NOT VERIFIED | UNKNOWN | UNKNOWN | N/A | N/A |

## 13. M21 Implementation Slices (evidence-derived, not the brief's example names)

1. **Finding → Readiness blocker integration** — *BLOCKING*. §9 proves Findings feed nothing into readiness. Screens: `maintenance/release-readiness`, drone/aircraft readiness panels. Backend: `release_readiness_service.py` (add a FINDING blocker class mirroring MATERIAL/COMPLIANCE/EVIDENCE). Data dependency: `Finding.status` (already exists). User value: an open Finding can no longer silently coexist with a READY status. LISA relevance: readiness answers become trustworthy only after this. Readiness relevance: direct. Depends on: nothing new (Finding model already complete).
2. **Drone-side Work Order / Inspection / Evidence / Compliance surfacing** — *PRODUCT-COMPLETION*. §7 shows these four stages exist for aircraft-linked assets but have zero drone-detail-page surface. Screens: `drones/[id]/page.tsx`. Backend dependency: confirm `WorkOrder`/inspection/evidence models already support `asset_id` filtering (per the same dual-FK pattern Finding uses) — likely additive-only. Depends on: none blocking, but logically follows slice 1 for maximal value.
3. **LISA drone context field** — *FOUNDATIONAL*. §8: `LisaConversationContext` has 10 real fields, none drone-scoped. Add `current_asset_id` (or `current_drone_id`) + entity-resolution wiring in `lisa.py`. Depends on: nothing blocking; unlocks M23.
4. **Drone-side Finding creation UX parity** — *CONSISTENCY*. `5eb955a` added the drone Findings *panel* (listing), but this session did not confirm (PARTIAL, §3.2) whether it also exposes create/disposition actions identical to `AircraftFindingsPanel`. If not, this is a small consistency slice.
5. **Dashboard mock-section elimination** — *POLISH*. `dashboard/page.tsx:16`'s mock findings import still feeds the "Maintenance Operations Snapshot" (self-labeled Illustrative Data). Replace with real aggregation once slice 1 exists so the label can be removed honestly.
6. **Navigation regrouping (Executive/Operations/Components/Inspections/Finance/Procurement/Intelligence as top-level groups)** — *CONSISTENCY*, per §6, sequenced after content slices per the existing M20 roadmap's own reasoning (don't create empty nav groups).
7. **RBAC UX parity on Findings detail page** — *POLISH*. §10's zero-match grep suggests no client-side permission gating exists on `/findings/[id]`; determine actual 403 UX behavior and add a disabled/hidden state if the experience today is a silent failure.
8. **Helicopter/eVTOL asset-type audit** — *FUTURE*. §16 — genuinely unaudited; needs its own investigation before any code.

## 14. M22 (Drone Readiness Intelligence) Dependencies

Per §7 and §9's gaps: M22 needs (a) slice 1 above (Finding→readiness wiring) done first — otherwise "drone readiness intelligence" would be built on an engine that already ignores an entire category of real defect data; (b) confirmation of whether flight hours/cycles and battery-health data are already inputs to any blocker class (this session found no evidence they are — `release_readiness_service.py` grep for "finding" found nothing, and battery/hours integration was not separately grepped this session — **UNKNOWN**, should be checked before scoping M22); (c) drone-side Work Order/Inspection surfacing (slice 2) so a "why is this drone not ready" answer can point at a real record the user can open, not just a status string.

## 15. M23 (Drone LISA Context) Dependencies

Per §8: M23 strictly needs slice 3 (a `current_asset_id`-equivalent field on `LisaConversationContext` plus resolution logic in `lisa.py`) before any drone-scoped LISA question can work end-to-end the way aircraft questions already can. It should also land after slice 1 (Finding→readiness) so LISA's readiness answers for drones are accurate once it can reach them at all. The `POST /ask` RBAC/retrieval-depth question flagged as unresolved in `M20_AUDIT_AND_ROADMAP.md` §1.5 ("whether it performs real RBAC-scoped retrieval or degrades to canned responses in some paths") was **not re-verified this session either** — carry forward as a precondition to confirm before M23, not just before a LISA redesign in general.

## 16. Architecture Reassessment Inputs

- **Knowledge Graph (Neo4j)**: confirmed by the M20 audit (not re-run this session — `grep -ril neo4j backend` was not re-executed) to be configured-but-unused. Nothing in this session's findings changes that; component genealogy and drone lifecycle data both remain renderable directly from Postgres rows without a graph DB.
- **Predictive Maintenance**: this session's readiness-gap finding (§9) is directly relevant — any predictive-maintenance layer proposed on top of the current readiness engine would inherit the same blind spot (Findings ignored) unless slice 1 lands first.
- **Event-Data Foundation**: Flight/battery/component installation-history data is real and tenant-scoped (per M20 audit, re-confirmed structurally via the drone route enumeration this session) — a reasonable foundation for an event log, but I did not check whether these tables are append-only/immutable or support update-in-place (which would matter for an event-sourcing reassessment) — **UNKNOWN**.
- **Integration Layer / AI Orchestration**: LISA's context model (§8) is the closest existing seam; its drone-blindness is the concrete gap this audit surfaces relevant to any AI-orchestration reassessment.

## 17. Critical Unknowns

- No live browser review was performed for any screen (dashboard, drone detail, aircraft detail, a work order, `/findings/[id]`) — stated explicitly per the task's own instruction, not glossed over.
- Deployed staging DB schema state as of the actual current HEAD (`5eb955a`) was not checked — `M20_RELEASE_VERIFICATION.md`'s deployment check was against `fce85bf`, one commit behind.
- Whether `5eb955a` has been pushed to `origin/main` — not checked this session (no `git fetch` run).
- Full-file reads of `release_readiness_service.py` (249 lines) and `globals.css` were not repeated this session; the readiness-blocker enumeration and full design-token inventory are carried from the prior M20 audit at PARTIAL confidence, not fresh VERIFIED.
- Whether flight hours/cycles or battery health feed any readiness blocker — UNKNOWN, not grepped this session.
- Actual RBAC UX behavior on a 403 (toast vs. crash vs. silent failure) on the Findings detail page — NOT VERIFIED, needs either a browser session or deeper code read.
- Whether helicopters/eVTOL are modeled at all (as an `Aircraft` subtype, a distinct `ComponentType`, or not at all) — genuinely UNKNOWN, not investigated this session per the brief's own flag that this was unaudited in M20 too.
- Full page-by-page generic-language scan (only the nav layer was scanned; in-page copy across 88 routes was not).
- Full breakpoint-by-breakpoint responsive behavior — code-inspection only, no rendering at any viewport size this session.

## 18. Recommended Execution Order

1. Finding → Readiness blocker integration (slice 1) — highest-leverage, smallest, most evidence-backed gap (§9), unblocks accurate answers everywhere else.
2. Confirm/complete drone Finding creation parity (slice 4) — cheap, closes an asymmetry this session could only partially verify.
3. Drone-side Work Order/Inspection/Evidence/Compliance surfacing (slice 2) — now that Findings correctly feed readiness, surfacing the underlying records makes the "why" answerable.
4. LISA drone context field (slice 3) — foundational for M23, independent of 1–3 but higher-value once readiness answers are trustworthy.
5. M22 (Drone Readiness Intelligence) — after 1 and (ideally) 3.
6. M23 (Drone LISA Context) — after slice 3 and the unresolved LISA RBAC/retrieval-depth question (§15) is actually re-verified, not assumed.
7. Dashboard mock-section elimination (slice 5) and RBAC UX parity (slice 7) — polish, can run in parallel with 2–4.
8. Navigation regrouping (slice 6) — deliberately last among the near-term slices, per the existing M20 rationale (don't create empty top-level nav groups before their content exists).
9. Helicopter/eVTOL audit (slice 8) — dedicated investigation session before any scoping, exactly as flagged unaudited twice now (M20 and this session).
