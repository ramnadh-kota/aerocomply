# M21.2 — Navigation / Application Shell IA Improvement

Date: 2026-09-20. Scope: navigation/shell IA only, built directly on `docs/M21_PRODUCT_UI_UX_AUDIT.md` (not re-run). No new pages, no new backend APIs, no visual redesign of feature pages, no LISA/AI/readiness-engine work.

## A. CURRENT BASELINE

- HEAD before changes: `d803acc` ("feat: integrate findings into asset readiness" — M21.1), branch `main`.
- `git status --short` before changes: working tree clean except the pre-existing set of untracked root-level `.md` audit reports and `frontend/AGENTS.md`/`frontend/CLAUDE.md` (none touched this session), consistent with the session's ground truth.

## B. ROUTE/IA FINDINGS

Re-read `frontend/components/layout/Sidebar.tsx` in full (209 lines) before changing anything, per the mission's requirement, rather than trusting the audit's summary alone.

- `Sidebar.tsx:21-100` (pre-change): tenant nav was 5 groups — **Overview** (12 items, a grab-bag: Dashboard, Notifications, Pilot Workflow, Executive, MRO Finance, 5 Procurement items, AI Command Center), **Fleet** (6), **Compliance** (7), **Maintenance** (19 — by far the largest, mixing Work Orders/Tasks/Technicians with Material/Release Readiness and Records), **Governance** (9, mixing Audit/Reports with Organization/Users/Roles/Plan/Workspace/Integrations/Settings). This matches the audit's §6 finding almost exactly (re-confirmed, not re-quoted).
- Three real routes had **zero nav entry anywhere** (confirmed via `Grep` across `frontend/components` for their paths — zero matches before this change): `/organization/readiness` (a "Commercial Pilot Readiness" checklist page, distinct from the M20 deployment/release-readiness engine — confirmed by reading its file), `/compliance/pre-audit`, `/compliance/regulatory-register`. These were unreachable from the UI entirely.
- Active-route logic (`Sidebar.tsx:122-125`, pre-change): `isActive()` already correctly handles both exact matches and dynamic detail routes (`pathname.startsWith(`${href}/`)`), with `/dashboard` and `/organization` deliberately exact-only to avoid false-positive highlighting. **This was NOT broken** — verified by reading the code and by browser-testing `/drones/{id}` (a dynamic detail route) against the `/drones` nav item, which highlighted correctly (§H). No fix was made because none was needed; this is stated explicitly rather than inventing a fix for a non-bug.
- The sidebar is a flat, always-rendered list of groups (no collapse/expand, no group highlighting) — there is no "parent group loses highlight on dynamic route" failure mode to fix, because groups themselves are never visually distinguished by active state, only individual `<Link>` items are.
- Permission-gating: **not zero**, contrary to what the mission's Phase-3 conditional anticipated. Two real mechanisms already existed and were left untouched: (1) `isPlatformUser` (`Sidebar.tsx:143-144`) switches the entire nav to a flat `PLATFORM_NAV_GROUPS` list using real `useSession().user.roles`; (2) `RoleSimContext.accessFor()` (prototype "view as role" simulation, explicitly documented as non-enforcing) dims/locks individual nav items per simulated role via `NAV_MODULE_MAP`.
- Mobile drawer: `SidebarDrawerContext` + a hamburger `TopBar` button already existed and worked correctly pre-change (browser-verified post-change, §H).

## C. IMPLEMENTED

- `frontend/components/layout/Sidebar.tsx`:
  - Replaced the 5 tenant `NAV_GROUPS` (Overview/Fleet/Compliance/Maintenance/Governance) with 7 groups following the real operational workflow, adapted to what exists in this repo: **Operations, Assets, MRO, Inspection & Evidence, Compliance, Resources, Administration**. Every `href` from the old groups was preserved (moved, not deleted or renamed) except for label wording ("Records" → "Maintenance Records" to disambiguate from Audit Trail/Documents per the audit's §5 observation; "Operations" → "Maintenance Operations" to disambiguate from the new top-level "Operations" group).
  - Added nav entries for the 3 previously-orphaned routes: `/organization/readiness` → "Pilot Readiness" (Administration), `/compliance/pre-audit` → "Pre-Audit" (Compliance), `/compliance/regulatory-register` → "Regulatory Register" (Compliance).
  - `PLATFORM_NAV_GROUPS`, `isActive()`, `RoleSimContext`/`NAV_MODULE_MAP` gating, the mobile drawer, and icon/glyph visual language: all left structurally unchanged (glyphs kept per-item as they were).
  - Exported `NAV_GROUPS`, `PLATFORM_NAV_GROUPS`, `NavGroup`, `NavItem`, and `isActive` (previously module-private) so the new structure is unit-testable without mounting React components (no RTL is configured in this repo).
- `frontend/tests/sidebar-navigation.test.ts` (new file): structural tests for the regrouped nav — see §G.
- No other files were touched. `Breadcrumbs.tsx` was read but not modified: it already renders a plain `Dashboard / <page>` trail (no group-name segment) and works unchanged with the new groups since it receives its `items` prop from each page, not from `Sidebar.tsx`.

## D. NEW NAVIGATION STRUCTURE

```
Operations
├─ Dashboard (/dashboard)
├─ Executive (/executive)
├─ Notifications (/notifications)
├─ Pilot Workflow (/pilot)
├─ Maintenance Control Center (/maintenance/control-center)
├─ Control Tower (/maintenance/control-tower)
├─ Hangar Floor (/maintenance/hangar)
├─ Automation Queue (/automation)
└─ AI Command Center (/ai)

Assets
├─ Fleet Health (/fleet/health)
├─ Aircraft (/aircraft)
├─ Drones (/drones)
├─ Engines (/engines)
├─ Components (/components)
└─ Facilities (/facilities)

MRO
├─ Work Orders (/maintenance/work-orders)
├─ Tasks (/maintenance/tasks)
├─ Planning (/maintenance/planning)
├─ Projects (/maintenance/projects)
├─ Technicians (/maintenance/technicians)
├─ Maintenance Operations (/maintenance/operations)
├─ Maintenance Program (/maintenance-program)
├─ Discrepancy Intelligence (/maintenance/discrepancies)
├─ Defects (/maintenance/defects)
├─ Deferred / MEL (/maintenance/deferred)
├─ Parts (/maintenance/parts)
├─ Material Readiness (/maintenance/material-readiness)
├─ Release Readiness (/maintenance/release-readiness)
└─ Maintenance Records (/maintenance/records)

Inspection & Evidence
├─ Inspections (/maintenance/inspections)
├─ Evidence (/evidence)
└─ Documents (/documents)

Compliance
├─ AeroComply (/compliance)
├─ Regulations (/regulations)
├─ Regulatory Register (/compliance/regulatory-register)   [newly linked]
├─ Assessments (/assessments)
├─ Assessment Intelligence (/assessment-intelligence)
├─ Pre-Audit (/compliance/pre-audit)                        [newly linked]
├─ Audit Trail (/audit)
└─ Data Import (/data-import)

Resources
├─ Procurement (/procurement)
├─ Parts Search (/procurement/parts)
├─ My Cart (/procurement/cart)
├─ Approvals (/procurement/approvals)
├─ Purchase Orders (/procurement/purchase-orders)
├─ Vendor Intelligence (/procurement/vendors)
└─ MRO Finance (/finance)

Administration
├─ Organization (/organization)
├─ Users (/organization/users)
├─ Roles (/organization/roles)
├─ Plan & Subscription (/organization/plan)
├─ Pilot Readiness (/organization/readiness)                [newly linked]
├─ Reports (/reports)
├─ Workspace (/workspace)
├─ Integrations (/integrations)
└─ Settings (/settings)

Platform Control Plane (unchanged, exclusive to PLATFORM_ADMIN/PLATFORM_STAFF)
├─ Organizations, Product Catalog, Plans, Audit/Activity, Approvals, Monitoring & Health
```

Dynamic detail routes (`/drones/[id]`, `/aircraft/[id]`, `/findings/[id]`, `/maintenance/work-orders/[id]`, etc.) are intentionally not listed items — they are reached contextually from their list pages, confirmed working end-to-end for `/drones/[id]` in §H.

## E. PERMISSIONS

No new permission-gating was added — the mission's conditional ("if Sidebar.tsx has zero permission-gating today, you may add it") did not apply, because two real mechanisms already existed and remain fully functional against the new groups (hrefs unchanged, so `NAV_MODULE_MAP` lookups in `RoleSimContext.tsx` still resolve correctly):
1. Real, session-backed: `isPlatformUser` swaps the entire nav to `PLATFORM_NAV_GROUPS` for `PLATFORM_ADMIN`/`PLATFORM_STAFF` roles from `useSession()`.
2. Prototype-only: `RoleSimContext`'s "view as role" simulation dims/locks individual tenant nav items — explicitly non-enforcing, browser-confirmed still functioning (the role selector dropdown was visible and interactive during verification, §H).

Backend authorization (`require_permission(...)` on every route) was not touched, read, or modified.

## F. RESPONSIVE

- **Desktop (1024×768 default pane size)**: VERIFIED in browser — all 7 groups render, correct active-state highlighting on list and dynamic-detail routes.
- **Mobile (375×812, emulated)**: VERIFIED in browser — sidebar collapses behind a hamburger (`TopBar`'s "Toggle navigation menu" button), drawer opens as an overlay showing the new grouped nav with no horizontal overflow, closes on nav-link click (existing `SidebarDrawerContext` behavior, unmodified).
- **Tablet**: NOT VERIFIED — not tested at 768×1024 this session; time-boxed after desktop+mobile confirmed no regressions from the pure data/label reorganization (no layout CSS was touched).

## G. TEST RESULTS

- New file `frontend/tests/sidebar-navigation.test.ts`: 12 tests covering (a) the 7 expected group labels in order, (b) no duplicate hrefs, (c) every item has href/label/glyph, (d) the 3 newly-linked orphan routes are present, (e) Assets/Inspection & Evidence group membership, (f) total tenant item count (56, up from 53 pre-change by exactly the 3 newly-linked routes), (g) `PLATFORM_NAV_GROUPS` unchanged (1 group, 6 items), (h) `isActive()` exact match, dynamic-detail-route match, non-match on siblings/prefix-overlap strings, and the `/dashboard`+`/organization` exact-only cases.
- Full suite: **166 passed / 0 failed** (baseline was 154 at `d803acc`; 166 = 154 + 12 new tests, confirming zero regressions).
- TypeScript (`npx tsc --noEmit`): **PASS** (no output/errors).
- ESLint (`npx eslint .`): **PASS** — 0 errors, 60 warnings, all 60 pre-existing (`react-hooks/set-state-in-effect` in unrelated files: `WelcomeTour.tsx`, `GlobalSearch.tsx`, `DataModeContext.tsx`, `alertState.ts`; one unused-eslint-disable in `lisa-matrix.test.ts`) — none introduced by this change, none in `Sidebar.tsx` or the new test file.
- Build (`npm run build`): **PASS** — full static/dynamic route manifest generated successfully, including `/organization/readiness` and both `/compliance/*` routes.

## H. BROWSER VERIFICATION

Started the existing local stack: backend already running locally on port 8001 (pre-existing from an earlier session, confirmed reachable via `Test-NetConnection`), frontend started via `preview_start` (`aerocomply-dev`, Next.js dev server, port 3000, "Ready in 399ms", no build errors in logs).

Flows actually driven:
1. Registered a throwaway local test organization/user via `POST /auth/register-organization` (`nav-qa-m212@example.com`, local DB only — not a real account, not staging/production).
2. Logged in through the real UI (`/login` → filled email/password → clicked "Sign in") — landed on `/dashboard`, confirmed the new "Operations" group renders first (Dashboard, Executive, Notifications, Pilot Workflow, Maintenance Control Center, Control Tower, Hangar Floor, Automation Queue, AI Command Center) followed by "ASSETS" section label and its items.
3. `read_page` confirmed the full rendered nav tree matches the new `NAV_GROUPS` structure exactly (Assets and MRO groups' hrefs cross-checked).
4. Navigated to `/drones` (empty state initially — fresh org, zero data) — confirmed no console errors.
5. Created one real drone (`NAVQA-1`) via `POST /drones` against the local backend to enable a real detail-page check.
6. Navigated to `/drones` in the browser — drone appears in the list, **"Drones" nav item correctly shows active/highlighted state**.
7. Clicked into `/drones/{id}` (a dynamic detail route not itself listed in the sidebar) — **confirmed the "Drones" nav item remains highlighted/active** on the detail route, per `isActive()`'s prefix-match logic.
8. Confirmed the Findings panel ("Findings (live)") is present and reachable on the drone detail page, matching the audit's finding that Findings should be contextual on asset detail pages rather than a top-level nav item.
9. Resized to mobile (375×812), reloaded `/dashboard`, confirmed the sidebar collapses to a hamburger with no horizontal overflow; clicked the "Toggle navigation menu" button and confirmed the drawer opens as an overlay showing the new grouped nav correctly.
10. Reset viewport to desktop, stopped the preview server.

Console errors: **none observed** at any point in this flow (`read_console_messages` with `onlyErrors: true` returned no logs after the drone-detail navigation).

Not driven this session: PLATFORM_ADMIN role verification (would require a second local user with that role and no practical way to self-assign it via the public registration endpoint in the time budget) — marked **NOT VERIFIED**. The `isPlatformUser` code path itself was read and is unchanged from before this session's edits, so its logic risk is unchanged, but its rendering was not re-confirmed live this session.

## I. BACKEND

**NO BACKEND CHANGES.** No backend file was read for modification purposes (only used the already-running local backend's public auth/drone endpoints to create test fixtures for browser verification). The pre-existing local backend process (port 8001) was not restarted, reconfigured, or otherwise touched beyond ordinary API calls a real user could make.

## J. SECURITY

- Confirmed by reading the diff (`git status --short` before/after) that only `frontend/components/layout/Sidebar.tsx` was modified and `frontend/tests/sidebar-navigation.test.ts` was added — no file under `backend/app/core/permissions.py`, any `require_permission` call site, or any auth/session file was touched.
- Confirmed the two existing sidebar-level visibility mechanisms (`isPlatformUser`, `RoleSimContext.accessFor`) were preserved verbatim; no new client-side data fetch was introduced for permission decisions, consistent with the mission's constraint to use only already-available session data (in this case, no new gating was added at all).
- Confirmed navigation labels/hrefs contain no tenant data, counts, or fabricated badges — every item is a static route string and label, matching the mission's prohibition on mock/fake nav content.
- Did not modify, weaken, or bypass any backend RBAC/tenant-isolation code; the sidebar remains, as before, a UX-only surface with the real boundary enforced server-side.

## K. REMAINING GAPS

- Tablet viewport (768×1024) not verified.
- PLATFORM_ADMIN nav rendering not re-verified live this session (code path unchanged; NOT VERIFIED per §H).
- Breadcrumbs were not extended to show a group-name segment (e.g. "Operations / Dashboard") — decided against it: `Breadcrumbs.tsx` is populated per-page from each page's own `items` prop, and the audit's Phase-3 guidance said to extend it only "minimally" if genuinely needed; since the sidebar itself now makes grouping visually clear via section labels, adding a group segment to every page's breadcrumb call site would have meant editing many feature pages, which is out of scope for a navigation/shell-only slice.
- "Records" ambiguity (per audit §5) addressed by renaming the nav label to "Maintenance Records"; the underlying page title/content at `/maintenance/records` itself was not touched (out of scope — that's page content, not shell).
- No group-level active-state highlighting exists (nor did it before) since the sidebar doesn't collapse/expand groups; this was confirmed to not be a bug needing a fix, not an oversight.

## L. GIT

- Final HEAD after changes: `a1a542e` ("feat: improve product navigation and application shell"), branch `main`, one commit ahead of `d803acc`.
- Commit hash: `a1a542e`. New commit, not an amend of `d803acc` or any prior commit. Contains exactly 2 files: `frontend/components/layout/Sidebar.tsx` (modified) and `frontend/tests/sidebar-navigation.test.ts` (new).
- Pushed: **NO**.
- Staging touched: **NO**.
- Production touched: **NO**.
