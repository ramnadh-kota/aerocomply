# M21.3 — Shared Product UI Foundation

Date: 2026-09-20. Scope: a small, evidence-based shared UI foundation plus a representative migration (Dashboard, Drones list, Drone detail, Findings display, Readiness display, one Maintenance page). Not a redesign of all ~88 pages, not a new design system, not a backend task.

## A. BASELINE

- Starting HEAD: `a1a542e` ("feat: improve product navigation and application shell" — M21.2), branch `main`.
- `git status --short` before changes: working tree clean except the pre-existing set of untracked root-level `.md` audit reports and `frontend/AGENTS.md`/`frontend/CLAUDE.md` (none touched this session).
- Read `M21_2_REPORT.md` and `docs/M21_PRODUCT_UI_UX_AUDIT.md` first, per the mission brief; did not re-run either audit.

## B. UI AUDIT

Read in full before writing anything: `frontend/app/globals.css` (design tokens, confirmed to exist from prior sessions), `frontend/components/status/StatusBadge.tsx` (298 lines, ~20 existing per-domain badge-mapping helper functions), `frontend/components/data-mode/RealDataPanel.tsx` (58 lines, loading/error/empty wrapper), `frontend/components/layout/Breadcrumbs.tsx`, `frontend/components/tables/DataTable.tsx`, and the six target pages/components (`dashboard/page.tsx`, `drones/page.tsx`, `drones/[id]/page.tsx`, `findings/[id]/page.tsx`, `RealReleaseReadinessPanel.tsx`, `maintenance/deferred/page.tsx`).

**Genuine duplication found, with file:line evidence:**

1. **Page-header pattern** — `<Breadcrumbs items={...}/>` immediately followed by `<div className="ac-section-header"><div><h1 className="ac-h1">…</h1><p className="ac-subtitle">…</p></div>{actions}</div>` was hand-rolled independently at: `drones/page.tsx:89-95`, `drones/[id]/page.tsx:370-384`, `findings/[id]/page.tsx:86-123` (with an eyebrow+badges variant), `dashboard/page.tsx`'s `RealFleetPanel` (108-115) and `RealFindingsPanel` (245-251), and `maintenance/deferred/page.tsx:122-128` and `:289-298` (two render branches, identical header). A grep for `ac-section-header` across `frontend/app` found 122 occurrences across 90 files, confirming this is the single most repeated structural pattern in the codebase, not a superficial coincidence.
2. **Readiness/blocker rendering** — two independently hand-rolled renderers for the same underlying concept (a READY/BLOCKED status badge plus a list of blockers, some linking to a Finding), with two different real API response shapes:
   - `drones/[id]/page.tsx:396-421` (pre-change): `readiness.blockers: string[]` matched by index against a parallel `finding_blockers[]` array.
   - `frontend/components/evidence/RealReleaseReadinessPanel.tsx:53-102` (pre-change): `readiness.blockers: { category, description, related_record_id }[]`.
   Both rendered a badge + `<ul>` of blocker text, with the FINDING category linking to `/findings/{id}` — same UX intent, different markup and different normalization logic duplicated in each file.
3. **Local status-badge helper functions reimplementing the same mapping** — three separate local functions all named `statusBadge` (plus one `severityBadge`) existed with overlapping logic that could be data-driven the same way `StatusBadge.tsx`'s existing ~20 exported helpers (`workOrderStatusBadge`, `maintenanceDueStatusBadge`, etc.) already are:
   - `drones/page.tsx:17-21` — `ACTIVE`→COMPLIANT, `GROUNDED`→NON_COMPLIANT, else UNKNOWN.
   - `drones/[id]/page.tsx:36-42` — superset: `ACTIVE|GOOD|READY`→COMPLIANT, `GROUNDED|CRITICAL|BLOCKED`→NON_COMPLIANT, else UNKNOWN.
   - `findings/[id]/page.tsx:20-36` — `severityBadge` (`CRITICAL|MAJOR`→NON_COMPLIANT else PENDING) and `statusBadge` (`CLOSED`→COMPLIANT, `IN_PROGRESS`→REVIEW_REQUIRED, else PENDING).

**Confirmed adequate, not touched:** `RealDataPanel.tsx` already provides consistent loading/error/empty chrome and is already adopted on every migrated page; no new Loading/Empty/Error primitive was justified by the evidence. `DataTable.tsx`, `Breadcrumbs.tsx`, and `StatusBadge.tsx`'s core badge-rendering function were all confirmed fit-for-purpose and left structurally unchanged (only additive helper exports were added to `StatusBadge.tsx`, no new badge visual language). No dashboard `ac-kpi-card-real` duplication with genuine *variation* was found beyond simple repetition of the same markup inline — not enough evidence to justify a new MetricCard component this pass, so none was built (see §K).

## C. IMPLEMENTED FOUNDATION

New files:
- `frontend/components/layout/PageHeader.tsx` — new.
- `frontend/components/readiness/ReadinessIndicator.tsx` — new.
- `frontend/tests/shared-ui-foundation.test.ts` — new.

Modified (additive only, no existing exports changed or removed):
- `frontend/components/status/StatusBadge.tsx` — added `assetStatusBadge`, `findingSeverityBadge`, `findingStatusBadge` exported helpers, following the file's existing per-domain-helper convention exactly.
- `frontend/components/evidence/RealReleaseReadinessPanel.tsx` — internal readiness rendering now delegates to `ReadinessIndicator`.
- `frontend/app/(app)/drones/page.tsx`, `frontend/app/(app)/drones/[id]/page.tsx`, `frontend/app/(app)/findings/[id]/page.tsx`, `frontend/app/(app)/dashboard/page.tsx`, `frontend/app/(app)/maintenance/deferred/page.tsx` — migrated per §E.

Total new/modified shared components: **2 new + 1 extended existing = 3**, well within the ~5-10 cap.

## D. COMPONENT API

- **`PageHeader({ breadcrumbs?, eyebrow?, title, subtitle?, actions? })`** — renders the existing `Breadcrumbs` component (if `breadcrumbs` given) followed by the existing `ac-section-header`/`ac-h1`/`ac-subtitle`/`ac-eyebrow` markup. Purely presentational; introduces no new CSS classes or visual language, just consolidates markup that was previously duplicated per-page.
- **`ReadinessIndicator({ status, blockers, footer? })`** + exported **`readinessStatusBadge(status)`** — renders a `StatusBadge` for `READY`/`BLOCKED`/other, followed by an optional `<ul>` of `ReadinessBlocker { key, label, href? }` items and an optional footer line. Callers normalize their own real API response shape into `ReadinessBlocker[]` before rendering; the component does not compute readiness or interpret blocker categories itself, matching the existing "presentation-only over the backend's own aggregation" principle already documented in `RealReleaseReadinessPanel.tsx`.
- **`assetStatusBadge(status)`**, **`findingSeverityBadge(severity)`**, **`findingStatusBadge(status)`** (in `StatusBadge.tsx`) — pure functions returning `{ status: BadgeKind, label: string }`, extracted verbatim (same mapping, same fallback behavior) from the three local duplicate functions found in §B.3.

## E. REPRESENTATIVE MIGRATION

- **Dashboard** (`dashboard/page.tsx`): top-level header and the `RealFleetPanel`'s header now use `PageHeader` (title/subtitle/`ViewingAsBadge` actions). No change to any data fetch, KPI computation, or the pre-existing "Illustrative Data" mock sections (left untouched, out of scope).
- **Drones list** (`drones/page.tsx`): header migrated to `PageHeader`; local `statusBadge` removed in favor of `assetStatusBadge` (imported aliased as `statusBadge` to keep the render call sites unchanged).
- **Drone detail** (`drones/[id]/page.tsx`): header migrated to `PageHeader`; local `statusBadge` removed in favor of `assetStatusBadge`; the Deployment Readiness block (battery/finding blockers) migrated to `ReadinessIndicator`, normalizing the existing `blockers: string[]` + `finding_blockers[]` (matched by index, exact same matching logic preserved, not changed) into `ReadinessBlocker[]`.
- **Findings display** (`findings/[id]/page.tsx`): the per-finding header (eyebrow "FINDING" / title / status+severity badges / dispose-close action buttons) migrated to `PageHeader` (badges passed via `subtitle`, buttons via `actions`); the plain loading-state breadcrumb kept as a direct `Breadcrumbs` call (see inline comment) since `PageHeader` requires a title and no generic one applies before the finding loads. Local `severityBadge`/`statusBadge` now delegate to the new `findingSeverityBadge`/`findingStatusBadge` StatusBadge.tsx exports with byte-for-byte identical mapping logic.
- **Readiness display** (`RealReleaseReadinessPanel.tsx`, used on work-order detail pages): rewritten to normalize its `{ category, description, related_record_id }[]` blocker shape into `ReadinessBlocker[]` and delegate rendering to `ReadinessIndicator`, so the same component now renders both the drone-detail and work-order readiness surfaces.
- **Maintenance** (`maintenance/deferred/page.tsx`): both render branches' header (mock-mode and REAL-mode) migrated to `PageHeader`.

No existing API call, hook, or business-logic branch was changed on any of these pages — only header/badge/readiness *markup* was consolidated.

## F. VISUAL/UX RESULTS

Observed directly in the browser (see §G): headers now render with identical spacing/typography across all six migrated surfaces (previously each page's `ac-section-header` block was hand-typed with minor structural drift, e.g. some wrapped subtitle in a `<p>` others didn't). The Deployment Readiness section on the drone detail page and the Release Readiness panel on work orders now share one component's blocker-list markup (bullet list, badge, blocker count) instead of two independently-styled renderers. Findings that block drone readiness link through correctly from the readiness blocker list to `/findings/{id}`, verified live (see §G) — the underlying Finding→readiness wiring itself was found already implemented in the running backend (not a gap this session needed to close; it contradicts one older finding in `docs/M21_PRODUCT_UI_UX_AUDIT.md` §9 which is now stale — see §K).

## G. RESPONSIVE VERIFICATION

Started the local stack: backend already running on port 8001 (confirmed via `Test-NetConnection`), frontend started via `preview_start` (`aerocomply-dev`, Next.js dev server, "Ready in 361ms").

Created real local test fixtures against the local backend only (no staging/production access): registered organization "M213 QA Org" (`POST /api/v1/auth/register-organization`), created drone `M213-QA-1` (`POST /api/v1/drones`), created a `CRITICAL` open Finding on that drone (`POST /api/v1/findings`), confirmed via `GET /drones/{id}/deployment-readiness` that the response was `{"status":"BLOCKED","blockers":["No battery assigned","Unresolved finding (CRITICAL): Cracked rotor arm"],"finding_blockers":[...]}`.

- **Desktop (1024×768 default pane size): PASS.** Logged in through the real UI (`/login`). Verified: Dashboard (both migrated `PageHeader` instances render correctly with live KPI data), Drones list (`assetStatusBadge` renders "ACTIVE" badge correctly), Drone detail (`ReadinessIndicator` renders "Blocked · 2 blockers" with both blocker lines, the finding blocker links to `/findings/{id}`), Findings detail (migrated `PageHeader` renders eyebrow/title/OPEN+CRITICAL badges/"No Action Required" button correctly), Maintenance/Deferred (migrated `PageHeader` renders with correct empty state). No visual regressions observed.
- **Mobile (375×812, emulated): PASS.** Drone detail and Dashboard reloaded at mobile width: hamburger menu present, no horizontal overflow, `PageHeader` and `ReadinessIndicator` both wrap/stack cleanly (title, subtitle, and action badges each on their own line). One unrelated, pre-existing behavior observed: the client-side session was not persisted across a full-page reload at this viewport (Dashboard showed "Sign in to view live fleet data" after reload) — this is existing `SessionContext`/token-storage behavior, not caused by this session's changes (not reproduced by clicking through the app normally), and out of scope to fix under this mission's boundaries.
- **Tablet (768×1024): NOT VERIFIED** — time-boxed after desktop and mobile confirmed no regressions from the presentation-only consolidation; no CSS breakpoint logic was touched by this change, so risk is low but explicitly unverified.

Console errors: only pre-existing Next.js dev-server HMR WebSocket noise (`ws://localhost:3000/_next/hmr...failed`, environment artifact of the sandboxed preview, not application code) and two `401` responses from a stale token refresh cycle that self-recovered (data loaded correctly on every page checked) — no error attributable to the new/changed components.

## H. TESTS

- New file `frontend/tests/shared-ui-foundation.test.ts`: 8 pure-function tests covering `assetStatusBadge` (COMPLIANT/NON_COMPLIANT/UNKNOWN branches), `findingSeverityBadge` (CRITICAL/MAJOR vs MINOR/OBSERVATION, preserving the exact prior behavior rather than merging severities), `findingStatusBadge` (CLOSED/IN_PROGRESS/OPEN), and `readinessStatusBadge` (READY/BLOCKED/fallback).
- `PageHeader` and `ReadinessIndicator` themselves are pure rendering components with no exported logic beyond the helpers above; this repo has no RTL configured (confirmed by following the exact convention of `tests/sidebar-navigation.test.ts`), so their JSX output was not independently unit-tested — verified instead by direct browser rendering (§G) on every page that uses them.
- Full suite: **174 passed / 0 failed** (baseline was 166 at `a1a542e`; 174 = 166 + 8 new tests, zero regressions).
- TypeScript (`npx tsc --noEmit`): **PASS** (no output/errors).
- ESLint (`npx eslint .`): **PASS** — 0 errors, 60 warnings, all 60 pre-existing and unrelated to any file touched this session (same set enumerated in `M21_2_REPORT.md`§G: `react-hooks/set-state-in-effect` in `WelcomeTour.tsx`, `GlobalSearch.tsx`, `DataModeContext.tsx`, `alertState.ts`, plus one unused-eslint-disable in `lisa-matrix.test.ts`).
- Build (`npm run build`): **PASS** — full static/dynamic route manifest generated successfully.

## I. SECURITY

No file under `backend/`, no `require_permission` call site, no auth/session file, and no RBAC/tenant-isolation code was read for modification or touched at all this session. All changes are confined to `frontend/components/layout/PageHeader.tsx` (new), `frontend/components/readiness/ReadinessIndicator.tsx` (new), `frontend/components/status/StatusBadge.tsx` (additive exports only), `frontend/components/evidence/RealReleaseReadinessPanel.tsx`, five `frontend/app/**/page.tsx` files, and one new test file. No new client-side permission logic was added or removed; the pages migrated retain their exact pre-existing `isAuthenticated`/`forbidden`/RBAC-adjacent branches unchanged (only the header/badge/readiness markup around them was consolidated).

## J. BACKEND

**NO BACKEND CHANGES.** The local backend's already-running process (port 8001) was used only via its existing public/authenticated API (`register-organization`, `POST /drones`, `POST /findings`, `GET /deployment-readiness`) to create test fixtures for browser verification — no backend file was read for modification purposes, no migration was run, and the process was not restarted or reconfigured.

## K. REMAINING UI GAPS

- The vast majority of the ~88 routes still use the pre-existing, unconsolidated `ac-section-header` markup directly (122 occurrences across 90 files per §B; only 7 call sites across 5 files were migrated to `PageHeader` this session). This was intentional per the mission's "representative migration, not a redesign" scope.
- No `MetricCard`/`DataCard` primitive was built: the dashboard's `ac-kpi-card-real` markup is repeated but not meaningfully *varied* across the pages checked this session — insufficient fresh evidence this pass to justify a 4th shared component; worth re-checking once more KPI-tile pages are audited.
- `docs/M21_PRODUCT_UI_UX_AUDIT.md` §9's claim ("Findings do NOT feed into readiness today... a `grep -n -i "finding"` on `release_readiness_service.py`/`readiness_service.py` returned zero matches") is now contradicted by this session's live `GET /drones/{id}/deployment-readiness` response, which correctly returned a FINDING-derived blocker. This is a **stale finding in that audit document**, not something this session changed — flagging it here since it was discovered incidentally while sourcing readiness fixtures for verification. The audit file itself was not modified (per the mission's explicit prohibition on editing prior report files).
- Tablet viewport (768×1024) not verified this session (§G).
- `PageHeader`'s `actions` slot on the Findings detail page nests interactive buttons inside what is otherwise a `subtitle`/badge-only convention on other pages — functionally fine (verified in-browser) but slightly less uniform than the Dashboard/Drones call sites; not worth a special-cased prop this pass.

## L. NEXT RECOMMENDED SLICE

Extend `PageHeader` adoption to the next tier of high-traffic pages identified in the M21.2 nav regrouping's "MRO" and "Compliance" groups (e.g. `maintenance/work-orders`, `maintenance/inspections`, `compliance`) — these were the next-most-linked pages per the new 7-group nav and already share the exact same `ac-section-header` pattern (confirmed present via the same grep in §B), making them low-risk, high-value follow-on migrations before considering any new shared component.

## M. GIT

- Final HEAD after changes: `253153c` ("feat: establish shared product ui foundation"), branch `main`, one commit ahead of `a1a542e`. Contains exactly 11 files: 4 new (`M21_3_REPORT.md`, `frontend/components/layout/PageHeader.tsx`, `frontend/components/readiness/ReadinessIndicator.tsx`, `frontend/tests/shared-ui-foundation.test.ts`) and 7 modified.
- Commit hash: `253153c`. New commit, not an amend of `a1a542e`, `d803acc`, or `5eb955a`.
- Pushed: **NO**.
- Staging touched: **NO**.
- Production touched: **NO**.
