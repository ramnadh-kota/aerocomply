# M20 — KOTA AEROSPACE OS: Audit (Phase 1) and Architecture Mapping (Phase 2)

Date: 2026-09-19
Scope: **Read-only audit and planning only.** No code was written or edited. No database was touched. No Phase 3+ work (dashboard rebuild, navigation changes, new components) was started this session. This report is a map for the user to pick a concrete next slice from — the same pattern as M18 (audit) → M19/M19.1/M19.2 (one verified slice each).

Prior context read in full before starting: `M18_LIVE_INTEGRATION_REPORT.md` (the file referenced as `M18_1_INTEGRATION_MATRIX.md` does not exist in this repo — confirmed by listing), `M19_REPORT.md`, `M19_1_REPORT.md`, `M19_2_REPORT.md`. This report does not repeat their screen-by-screen mock/live inventory — it extends it toward the specific new concepts the master prompt introduces that those reports did not cover: dashboard KPIs/charts, Findings/Dispositions as first-class records, component genealogy, LISA's actual implementation, the existing design system, MroStateContext/RoleSimContext, the readiness engine's actual scope, role-based dashboards, navigation restructure, and the graph-DB question.

---

## PHASE 1 — AUDIT

### 1.1 Frontend routing structure vs. target navigation

`frontend/components/layout/Sidebar.tsx:21-120` defines the real, live navigation (not aspirational). It is grouped as **Overview, Fleet, Compliance, Maintenance, Governance** (`Sidebar.tsx:21-100`), plus a completely separate, deliberately-flat **Platform Control Plane** nav shown only to `PLATFORM_ADMIN`/`PLATFORM_STAFF` (`Sidebar.tsx:108-120`).

Mapping to the master prompt's target groups (Overview/Executive/Fleet/Operations/Maintenance/Components/Inspections/AeroComply/Intelligence/Reports/Finance/Procurement/Governance):

| Target group | Current state |
|---|---|
| Overview | Exists (`Sidebar.tsx:23`), but is a grab-bag: Dashboard, Notifications, Pilot Workflow, Executive, Finance, Procurement (5 sub-items), AI Command Center — Finance/Procurement/Executive are really their own domains bundled in here today. |
| Executive | A single nav item (`/executive`, `Sidebar.tsx:28`) inside Overview, not its own group. Page exists (`frontend/app/(app)/executive/page.tsx`). |
| Fleet | Exists as its own group (`Sidebar.tsx:40-49`): Fleet Health, Aircraft, Engines, Components, Facilities, Drones. |
| Operations | **Does not exist as a named group.** Operational items are split across Maintenance (`/maintenance/operations`, `/maintenance/control-center`, `/maintenance/hangar`) and Overview (`/pilot`). |
| Maintenance | Exists, is the largest group (`Sidebar.tsx:62-85`, 18 items) — arguably already needs splitting, not expanding. |
| Components | A route exists (`/components`, inside Fleet) but not a standalone nav group with sub-structure. |
| Inspections | A route exists (`/maintenance/inspections`) nested under Maintenance, not its own top-level group. |
| AeroComply | Exists as `/compliance` inside the "Compliance" group (labeled "AeroComply" in the nav, `Sidebar.tsx:53`) alongside Regulations, Assessments, Assessment Intelligence, Data Import, Evidence, Documents. |
| Intelligence | **Does not exist as a concept/group.** Closest existing things are AI Command Center (`/ai`) and Assessment Intelligence (`/assessment-intelligence`) — both under different groups, not unified. |
| Reports | Exists as one item under Governance (`Sidebar.tsx:90`). |
| Finance | Exists as one item under Overview (`Sidebar.tsx:29`), not its own group. |
| Procurement | Exists as 5 items under Overview (`Sidebar.tsx:30-34`). |
| Governance | Exists as its own group (`Sidebar.tsx:87-99`): Audit Trail, Reports, Organization×3, Workspace, Integrations, Settings. |

**Conclusion**: nearly every target *route* already exists somewhere; what's missing is the *regrouping* — Executive, Operations, Components, Inspections, Finance, Procurement, and Intelligence all need to become real top-level groups instead of being buried inside Overview/Fleet/Maintenance/Governance. This is a navigation-restructure task, not a net-new-page task, for the vast majority of it.

### 1.2 Current dashboard implementation

`frontend/app/(app)/dashboard/page.tsx` (475 lines) — **entirely mock-data-backed** (confirmed, matches M18's finding). Imports directly from `lib/mock/assessments`, `lib/mock/aircraft`, `lib/mock/evidence`, `lib/mock/maintenance`, `lib/mock/maintenanceProjects`, `lib/mock/workOrders`, `lib/mock/technicians`, `lib/mock/inspectorReviews`, `lib/mock/findings`, and a derived `lib/mock/ai/analytics.ts` layer (`dashboard/page.tsx:1-14`).

What already renders (real components, mock data):
- `AircraftContextLayer` hero visual (`dashboard/page.tsx:66`)
- `DailyBriefCard`, `OperationalPriorityQueue`, `FleetTatSummary` (`dashboard/page.tsx:73-81`) — pre-built dashboard widget components already exist at `frontend/components/dashboard/*`
- A 5-KPI grid: Total Aircraft, Applicable Requirements, Assessments Requiring Review, Insufficient Data, Critical Compliance Issues (`dashboard/page.tsx:23-28`)
- A compliance-status distribution bar (Compliant/Review Required/Insufficient Data/Non-Compliant, `dashboard/page.tsx:31-35`)
- An "Operational Attention"-shaped block already exists conceptually: `ATTENTION_ITEMS` (`dashboard/page.tsx:38-42`) — hardcoded array, not derived from any engine
- A second KPI row for Maintenance (Active Projects, Open Work Orders, etc.)
- `CoreLoopDiagram` ("The AeroComply Loop")

Gap vs. target KPI/chart list: **no charts at all today** (no Fleet Readiness Over Time, no Maintenance Workload chart, no Component Life Exposure chart) — every number is a static KPI tile, never a time-series or distribution chart. No consolidated backend endpoint exists to back any of it (confirmed already in M18 Section 2, item 3 — still true, re-confirmed this session by absence of any `/dashboard` or `/analytics` router in `backend/app/api/v1`).

### 1.3 Findings/Dispositions domain model

**Findings: partially real, but narrower than the master prompt's concept.** `backend/app/models/assessment.py:111-134` defines a real, tenant-scoped `AssessmentFinding` table — genuinely a first-class record (category, severity, title, description, `entity_type`/`entity_id` traceability, `materiality_score`, `complexity_band`, `priority_rank`, `source`, `resolved` boolean), not free text. **However it is scoped exclusively to the compliance-assessment engine** — it always belongs to an `AssessmentSnapshot` (`assessment.py:120-122`, `snapshot_id` FK, `nullable=False`) and is written by the assessment/gap-analysis pipeline, not by inspections, maintenance findings, or general MRO discrepancies. There is no generic "Finding" concept usable from an inspection or a work order.

`AssessmentRisk` and `AssessmentGap` (`assessment.py:139-171`) both optionally reference a `finding_id` and carry `recommended_action`/`mitigation`/`owner_role` fields — the closest thing to a "Disposition" in the backend, but again scoped only to the assessment engine, and there is **no dedicated `Disposition` model, table, or lifecycle (proposed → approved → closed) anywhere in `backend/app/models/`** (confirmed: `grep -ril "disposition" backend/app/models` matched nothing beyond the same `assessment.py`/`part.py` hits already covered).

Separately, `frontend/lib/mock/findings.ts` exists and is consumed live by the dashboard (`checklistExceptions = findings.filter((f) => f.requiresDefect)`, `dashboard/page.tsx:58`) — this is a **different, unrelated mock concept** (checklist-exception findings tied to inspections), not wired to the real `AssessmentFinding` backend table at all. So today there are two unrelated "Findings" concepts: one real-but-narrow (assessment engine) and one mock-and-disconnected (checklist exceptions).

**Evidence**: confirmed still real and live per tonight's earlier work — `backend/app/models/evidence.py` backs `POST/GET /evidence/{id}`, `/evidence/{id}/files`, `/transition`. M18's Section 1.5 finding still holds: the mock `evidenceRepository` UI model and the real `BackendEvidence` shape are materially different (document/record-linkage model vs. task-status-lifecycle model) — this was correctly not touched in M18 and remains a real reconciliation task, not yet started.

### 1.4 Component lifecycle/traceability vs. genealogy visualization

Backend: `backend/app/models/component.py` (`Component`, `ComponentType`, `ComponentStatus`) and `backend/app/models/installation_history.py` (`BatteryInstallation`, `ComponentInstallation`) are real, tenant-scoped tables recording install/removal history per component per asset — this is genuine lineage data, not mock.

Frontend: `frontend/lib/mock/partTraceability.ts` exists and is consumed by `frontend/lib/domain/repositories.ts:26` (`certificatesForPart`) — **mock only**, and it's about part *certificates*, not an install/removal genealogy graph. `grep` for "genealogy"/"traceability" across `frontend/app`, `frontend/components`, `frontend/lib` found no dedicated graphical/tree/genealogy visualization component anywhere — only scattered text mentions in unrelated pages (compliance pre-audit, finance, cannibalization mock, etc.) and the `partTraceability` mock file itself. **Conclusion: no component genealogy visualization exists in any form (not even a rough prototype)** — the backend data to build one from (`ComponentInstallation` rows) is real, but nothing renders it as a graph/tree today. This is the one target concept that is genuinely net-new on the frontend with a real backend already available to build on.

### 1.5 LISA / AI implementation

`frontend/app/(app)/ai/page.tsx` is a thin wrapper (36 lines) around `frontend/components/ai/AIConsole.tsx`, taking `initialProjectId`/`initialAircraftId`/`initialQuestion` from query params. Backend: `backend/app/api/v1/lisa.py` exposes real routes — `POST /ask`, `GET /context`, `POST /context/reset` (`lisa.py:16,53,64`) — backed by a real, tenant-scoped `LisaConversationContext` model (`backend/app/models/lisa_conversation_context.py`) that tracks `current_aircraft_id`, `current_work_order_id`, `current_task_id`, `current_part_id`, `current_part_requirement_id`, `current_procurement_request_id`, `current_vendor_id`, `current_purchase_order_id`, `current_technician_user_id`, `current_aog_event_id`, plus a JSON-encoded `recent_entities`/`recent_questions` list — **this is already, structurally, a contextual-retrieval design** (every `current_*_id` is documented in the model's own docstring as "a real backend record's primary key — never a fabricated identifier"), not a generic chatbot data model. This is a meaningfully more solid foundation than the master prompt's framing ("redesigned... not a generic chatbot") assumes — the contextual-entity-resolution backbone already exists.

What was **not** verified this session (would need a dedicated follow-up, not attempted here per the read-only/no-Lisa-code-touch boundary respected by M19/M19.1/M19.2 too): whether `POST /ask` actually performs RBAC-scoped retrieval against real records end-to-end, or degrades to canned/mock responses in some paths, and the specific PERMISSION_DENIED finding referenced from "tonight's overnight QA" was not independently re-confirmed this session (no overnight-QA report file matching that description was found among the untracked `.md` files at repo root to cite precisely — the closest are `M17_OVERNIGHT_*` reports, not read this session since Phase 1 scope was the *new* master-prompt concepts, not re-auditing M17). **This should be explicitly re-verified, not assumed, before any LISA redesign work begins.**

### 1.6 Design system / theme

`frontend/app/globals.css` already implements almost exactly the requested direction, not a green-field task:
- Dark theme base: `--ac-bg: #050b14`, `--ac-bg-elevated: #0b1624`, `--ac-bg-surface: #0e1b2a` (`globals.css:69-71`) — a near-black navy ground, explicitly comment-labeled "retinted toward the mission-control navy/cyan reference palette... near-black navy ground, cool blue-gray surfaces/borders" (`globals.css:64-68`).
- Accent: `--ac-accent: #2563eb` / `--ac-accent-hover: #1d4fc4` (`globals.css:22-23`) — a blue accent, not yet the specific "KOTA electric blue" the prompt names, but the same design direction.
- Status colors already exist as CSS variables: `--ac-status-compliant`, `--ac-status-review`, `--ac-status-insufficient`, `--ac-status-non-compliant`, `--ac-status-unknown` (`globals.css:26`, `84`, badge classes at `globals.css:810-843`), including a distinct **unknown** status color/badge (`ac-badge-unknown`, `globals.css:822`) — i.e. the "UNKNOWN != FALSE" principle already has a first-class visual treatment in the design system, not something to invent.

No separate design-tokens file or Tailwind config was found (`find frontend -maxdepth 1 -iname "tailwind*"` returned nothing) — this app does not use Tailwind; all theming is hand-written CSS custom properties in `globals.css`. **Conclusion: the design system is EXISTS AND MOSTLY SOLID**, needs accent-color tuning and probably a `prefers-reduced-motion` audit (not checked this session), not a rebuild.

### 1.7 MroStateContext, RoleSimContext, repository abstraction, engines

All three confirmed real and exactly as scoped, not just referenced aspirationally:
- `frontend/lib/mro-state/MroStateContext.tsx` (329 lines) — its own header comment states plainly: "this is still a prototype: everything here is in-memory React state... never persisted to a backend and resets on a full page reload" (`MroStateContext.tsx:15-19`). It exists to keep the technician-checklist submission and inspector-decision review coherent within one client session — a real, useful, but explicitly non-persistent abstraction.
- `frontend/lib/role-sim/RoleSimContext.tsx` (93 lines) — its own header comment: "purely visual/UI simulation... does NOT enforce anything, does not gate any data fetch, and is not a real authorization system" (`RoleSimContext.tsx:2-6`). Drives `Sidebar.tsx`'s `accessFor()` gating of which nav items *show*, nothing more — real RBAC enforcement is separately confirmed (M19/M19.1/M19.2) to live entirely server-side via `require_permission`.
- `frontend/lib/domain/repositories.ts` (294 lines) — real, already in active use for at least the evidence-detail page per its own header comment (`repositories.ts:1-16`); today every repository implementation is "a thin wrapper around the SAME existing mock helpers... swapping the mock implementation for a real database-backed one later means changing only this file" — i.e. it's a seam that exists but has not yet been used to swap any screen to live data.
- Single AI engine / report engine / audit engine: no dedicated `report_engine`/`audit_engine` module was found as a named abstraction in `backend/app/services/`; audit is handled via `AuditEvent` rows written inline by services (confirmed pattern in M19.1/M19.2's own audit-event verification) rather than a centralized "audit engine" class — functionally real and consistent, just not literally named that.

### 1.8 Role-based dashboard variation

None exists today. `dashboard/page.tsx` renders one fixed layout for every user; the only per-role UI variation anywhere in the app is `RoleSimContext`'s nav-item visibility toggle (Section 1.7) — there is no alternate dashboard composition for Executive vs. Maintenance Manager vs. Technician. The `/executive` route (`frontend/app/(app)/executive/page.tsx`) is a **separate, standalone page**, not a role-conditional rendering of the same dashboard — worth noting as a possible starting seam (an "Executive view" already exists as its own page; the master prompt's "role-based dashboards" concept could reuse that pattern rather than inventing conditional rendering inside one page).

### 1.9 Readiness engine(s) — drone-only or fleet-wide?

`backend/app/services/readiness_service.py` (80 lines) and `backend/app/services/release_readiness_service.py` (249 lines) were both re-read this session. **Correction to the master prompt's framing: this is not drone-only.** `release_readiness_service.py:35` (`evaluate_deployment_readiness`) and its own in-line comment explicitly generalize across both: *"Work orders with no asset_id (e.g. drone-only work orders with neither aircraft_id nor asset_id set) simply have no COMPLIANCE..."* (`release_readiness_service.py:39-40`) — i.e. the engine already branches on whether a work order is aircraft-linked (`aircraft_id`) or drone-linked (`asset_id`/none), and the MATERIAL-blocker work proven tonight (commits `23dcda5`/`abc2e86`) exercised this same shared engine, not a drone-specific copy. **There is one readiness engine, already fleet-generic in structure**, not two, and not drone-only — this is a stronger starting position than the master-prompt language ("drone-focused") assumed.

### 1.10 Graph DB (Neo4j)

Confirmed: `backend/app/core/config.py` and `backend/.env.example` are the **only** two files in the entire backend referencing Neo4j (`grep -ril neo4j backend` → exactly these two). No Neo4j driver import, no graph-query code, no service using it anywhere in `backend/app/services` or `backend/app/api`. **Conclusion: Neo4j is configured (connection fields exist) and completely unused** — confirms the master prompt's own instruction (PostgreSQL is source of truth, graph DB derived-only) is currently trivially true only because nothing derives into it yet. Any component-genealogy graph work (Section 1.4) could either use Neo4j for the first time or, more cheaply, render the graph client-side directly from `ComponentInstallation` Postgres rows without touching Neo4j at all — the latter is far lower-risk for a first slice.

### 1.11 Public marketing website boundary

Confirmed there is **no separate marketing app/package** in this repo — `find` shows only `frontend/app/page.tsx` (the root `/` route) as a distinct, unauthenticated splash page, consistent with M17-era findings ("prototype... not connected to backend"). There is no `apps/marketing`, no separate Next.js project, no distinct deploy target for a marketing site. **Documented boundary for future sessions: `frontend/app/page.tsx` (and only that one file/route) is the public marketing surface; everything under `frontend/app/(app)/**` is the authenticated application and is the only area any KOTA AEROSPACE OS work should touch.**

---

## PHASE 2 — ARCHITECTURE MAPPING

| Concept | Classification | Basis |
|---|---|---|
| Design system (colors/dark theme/status colors) | **ALREADY EXISTS AND SOLID** | `globals.css` navy/blue palette + 5-state status colors incl. `unknown`, already close to spec (§1.6) |
| Readiness engine | **ALREADY EXISTS AND SOLID** (fleet-generic, not drone-only) | `release_readiness_service.py` branches on aircraft/asset already; MATERIAL blocker proven tonight (§1.9) |
| Repository abstraction / MroStateContext / RoleSimContext | **ALREADY EXISTS, EXPLICITLY SCOPED AS PROTOTYPE** | Real, working, but self-documented as non-persistent/non-enforcing seams, not final architecture (§1.7) |
| LISA contextual backbone (conversation context, entity resolution) | **ALREADY EXISTS, SOLID FOUNDATION, NEEDS VERIFICATION + UI REWORK** | Real tenant-scoped model + 3 real endpoints already entity-aware; RBAC-scoped retrieval and any mock-degradation paths unverified this session (§1.5) |
| Findings (assessment-engine scope) | **PARTIALLY EXISTS** | Real, well-modeled `AssessmentFinding`/`Risk`/`Gap` — but scoped only to the compliance-assessment pipeline, not general MRO/inspection findings (§1.3) |
| Findings (general/inspection scope) & Dispositions | **DOES NOT EXIST AT ALL** (backend); a disconnected mock exists (frontend) | No `Disposition` model anywhere; `lib/mock/findings.ts` is a different, unrelated, mock-only concept already live on the dashboard (§1.3) |
| Evidence | **ALREADY EXISTS AND SOLID (backend); frontend detail model mismatch unresolved** | Confirmed real per M18 §1.5; mock UI shape vs. backend shape reconciliation still not started (§1.3) |
| Component install/removal history (backend data) | **ALREADY EXISTS AND SOLID** | `Component`/`ComponentInstallation`/`BatteryInstallation` real, tenant-scoped (§1.4) |
| Component genealogy visualization (frontend) | **DOES NOT EXIST AT ALL** | No graph/tree/genealogy UI found anywhere; only an unrelated `partTraceability` mock (§1.4) |
| Dashboard KPI tiles | **PARTIALLY EXISTS** | Real layout/components, 100% mock data, no backend aggregation endpoint (§1.2) |
| Dashboard charts (time-series, workload, life-exposure) | **DOES NOT EXIST AT ALL** | Zero charts anywhere in the current dashboard — only static KPI numbers (§1.2) |
| "Operational Attention" panel | **DOES NOT EXIST (as a derived engine)**; a static placeholder exists | `ATTENTION_ITEMS` is a hardcoded array, not computed from any real condition (§1.2) |
| Role-based dashboards | **DOES NOT EXIST**, but a reusable seam exists | No per-role dashboard composition; `/executive` as a separate page is a usable pattern to extend (§1.8) |
| Navigation restructure (Executive/Operations/Components/Inspections/Intelligence/Finance/Procurement as top-level groups) | **EXISTS BUT NEEDS REWORK** | Nearly every target route exists today, just grouped differently (§1.1) — a regrouping task, not new-page work |
| Graph DB / Neo4j | **CONFIGURED, ENTIRELY UNUSED** | Two config references only, zero code paths (§1.10) |
| Asset Command View (per asset type) | **DOES NOT EXIST AT ALL** | Not investigated as a distinct existing pattern this session beyond confirming no dedicated component/page name matches it; treat as net-new until a follow-up audit specifically checks for it |
| Helicopter/eVTOL extensibility | **NOT AUDITED THIS SESSION** | Out of this session's specific concept list; `ComponentType`/`AircraftDetail` models were not read closely enough to classify — flag as unknown, not "does not exist," pending a dedicated check |

---

## Proposed milestone roadmap (sequenced, each scoped to one real session)

1. **M20.1 — LISA RBAC/retrieval verification (audit-then-fix-if-needed).** Before any LISA redesign, actually drive `POST /ask` end-to-end with a real browser/curl against two different roles and confirm (a) it retrieves real records via `LisaConversationContext`'s entity-resolution fields, not canned text, and (b) a role without read access to an entity type genuinely gets denied, not just UI-hidden. This directly resolves the unconfirmed "PERMISSION_DENIED" reference from §1.5 before it's designed around.
2. **M20.2 — General Finding/Disposition backend model.** Design and ship a tenant-scoped `Finding` + `Disposition` pair usable from inspections and work orders (not just the assessment engine), following the same `entity_type`/`entity_id`-traceable pattern `AssessmentFinding` already establishes (§1.3) — reuse the pattern, don't invent a new one. Small, testable, no UI yet.
3. **M20.3 — Wire the disconnected mock Findings on the dashboard to the new real model** (replacing `lib/mock/findings.ts`'s dashboard usage, §1.2/1.3), and reconcile the Evidence detail mock-vs-backend shape mismatch flagged since M18 §1.5 — both are "connect existing real backend to existing UI" work, the highest-proven-success pattern from tonight's M18/M19 sessions.
4. **M20.4 — One real dashboard KPI backed by a real aggregation endpoint** (e.g. "Open Findings" or "Maintenance Due" sourced from `fleet/maintenance-due` + the new Finding model), replacing exactly one mock KPI tile end-to-end, browser-verified — not the whole dashboard. Establishes the aggregation-endpoint pattern the other KPIs/charts will reuse.
5. **M20.5 — Component genealogy, read-only, backend-data-driven, no Neo4j.** Render `ComponentInstallation`/`BatteryInstallation` history as a simple timeline or tree for one component, straight from Postgres via a new small endpoint — explicitly skip Neo4j for v1 (§1.10) since the data doesn't need a graph DB to be useful, and a working read-only view is a much smaller, fully-verifiable slice than a new graph subsystem.
6. **M20.6 — Navigation regrouping.** Once 2–3 of the above have added real content to justify it, restructure `Sidebar.tsx`'s groups (Executive, Operations, Components, Inspections, Finance, Procurement, Intelligence as real top-level groups per §1.1) — deliberately sequenced *after* content work, not before, so the new groups aren't empty shells.
7. **M20.7 — Role-based dashboard variation**, extending the existing `/executive` page pattern (§1.8) to 1–2 more roles (e.g. Maintenance Manager), once the underlying dashboard has enough real (non-mock) content from M20.3/M20.4 to make per-role variation meaningful rather than per-role reshuffling of the same mock numbers.
8. **Not scheduled yet, deliberately**: full chart library integration (Fleet Readiness Over Time, workload, life-exposure charts), the full Operational Attention derived-panel engine, Asset Command View, and helicopter/eVTOL extensibility — each needs its own dedicated audit-first session before scoping, per §1.11's "Asset Command View" and "helicopter/eVTOL" rows being explicitly marked unaudited rather than guessed at.

### Recommended first concrete milestone: **M20.2 — General Finding/Disposition backend model**

This is the best-founded, highest-leverage starting point for three reasons. First, it has the strongest existing pattern to extend rather than invent: `AssessmentFinding` (§1.3) already proves the exact traceable-record shape (`entity_type`/`entity_id`, severity, materiality, source, resolved) this needs — this is "widen an existing well-designed table's scope," the same low-risk shape as M19.1's reuse of `AuthVerificationCode` for invitations rather than a new token system. Second, it unblocks the two next-highest-value items in the roadmap: the dashboard's "Open Findings" KPI (§1.2) and the disconnected mock-Findings-on-dashboard problem (§1.3) both need this model to exist before either can be honestly wired to real data — starting here avoids doing dashboard work tweice. Third, it matches the master prompt's own stated emphasis (Findings/Dispositions "as first-class records," and the dashboard/readiness/findings/evidence chain named explicitly as the priority) more directly than starting with navigation or visual redesign, which would be cosmetic without this underlying data first.
