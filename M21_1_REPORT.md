# M21.1 — Findings → Readiness Blocker Integration

Date: 2026-09-20. Builds directly on `docs/M21_PRODUCT_UI_UX_AUDIT.md` §9's finding
(`grep -n -i "finding" release_readiness_service.py readiness_service.py` returned
zero matches as of HEAD `5eb955a`): unresolved Findings had no effect on either
readiness engine. This slice closes that gap with pure domain wiring — no new
Finding model, no new readiness engine, no drone-specific logic, no AI/LLM
involvement.

## A. IMPLEMENTED

Unresolved Findings (status `OPEN` or `IN_PROGRESS`) now produce an explainable
blocker in **both** existing readiness engines:

1. `release_readiness_service.py` (work-order-scoped, MATERIAL/COMPLIANCE/EVIDENCE
   pattern) — added a `FINDING` blocker category.
2. `readiness_service.py` (asset-scoped drone deployment-readiness) — added
   unresolved-Finding detection alongside the existing status/battery/maintenance/
   inspection blockers.

Both reuse the existing `Finding` model/API/service from M20.2 verbatim — no
schema changes to `Finding` itself, no migration (verified: `alembic current` on
the local dev DB is already at head `0036`, and `\d findings` in Postgres matches
the model exactly).

## B. BUSINESS RULE

**A Finding blocks readiness if and only if its status is not `CLOSED` (i.e.
`OPEN` or `IN_PROGRESS`).** This is exactly the instruction-giver's suggested
default, adopted unchanged after reading `app/models/finding.py` in full: there
is no existing field on `Finding` representing airworthiness/operational impact
independent of `status`, and there is no existing codebase precedent anywhere
(MATERIAL/COMPLIANCE/EVIDENCE/INSPECTION/TASK_EXECUTION) for a severity-based
"does this block" split — every existing blocker category is a binary
satisfied/not-satisfied gate, not a severity-weighted one. Severity
(`CRITICAL`/`MAJOR`/`MINOR`/`OBSERVATION`) is **surfaced** in every blocker's
description/payload for explainability, but is **never** used to decide whether
a Finding blocks. One blocker per unresolved Finding — never collapsed, even
when multiple Findings exist on the same asset/work order.

## C. BACKEND (files/APIs changed)

- `backend/app/models/finding.py` — **unchanged** (read-only reuse: `Finding`,
  `FindingStatus`, `FindingSeverity`).
- `backend/app/schemas/release_readiness.py` — added `"FINDING"` to the
  `BlockerCategory` Literal (was `EVIDENCE|INSPECTION|TASK_EXECUTION|MATERIAL|COMPLIANCE`).
- `backend/app/services/release_readiness_service.py` —
  `get_release_readiness_for_work_order()` now runs one additional query
  (`select(Finding).where(organization_id=..., status != CLOSED, or_(work_order_id==wo.id, asset_id==wo.asset_id, aircraft_id==wo.aircraft_id))`)
  and appends a `Blocker(category="FINDING", description=f"Unresolved finding
  ({severity}): {title!r} (status={status!r})", related_record_id=finding.id)`
  per row. Single query, no per-task/per-asset loop (see §J).
- `backend/app/schemas/drone_ops.py` — added `FindingBlocker` model
  (`finding_id`, `title`, `severity`, `status`) and a new
  `finding_blockers: list[FindingBlocker] = []` field on
  `DeploymentReadinessResponse` (existing `blockers: list[str]` field
  unchanged/backward-compatible).
- `backend/app/services/readiness_service.py` —
  `evaluate_deployment_readiness()` now runs one additional query
  (`select(Finding).where(organization_id=..., asset_id=..., status != CLOSED)`),
  appends `f"Unresolved finding ({severity}): {title}"` to the existing
  `blockers: list[str]`, and returns the same data structurally in the new
  `finding_blockers` list.
- `backend/app/api/v1/drones.py` and `backend/app/api/v1/release_readiness.py` —
  **unchanged** (both already pass the service's dict/model straight through).

No new permission was added — Finding reads/writes still gate on
`Permission.INSPECTION_READ`/`INSPECTION_WRITE` exactly as before (M20.2's own
established precedent of not adding a narrower permission).

## D. FRONTEND (files/components changed)

- `frontend/lib/api/release-readiness.ts` — added `"FINDING"` to
  `BackendBlockerCategory`.
- `frontend/components/evidence/RealReleaseReadinessPanel.tsx` — added a
  `"Finding"` label to `CATEGORY_LABEL`; a `FINDING`-category blocker now
  renders a `(view finding)` link to `/findings/{related_record_id}` instead of
  the raw UUID span the other categories still show.
- `frontend/lib/api/drones.ts` — added `FindingBlocker` interface and optional
  `finding_blockers?: FindingBlocker[]` field on `DeploymentReadinessResponse`.
- `frontend/app/(app)/drones/[id]/page.tsx` — the Deployment Readiness blocker
  list now links each string blocker that has a matching `finding_blockers`
  entry (matched positionally — the backend always appends finding blockers
  last) through to `/findings/{finding_id}`; no new findings list was built
  inside the readiness panel, per instruction (link out to the existing M20.4
  canonical page only).
- No changes to `DroneFindingsPanel`, `AircraftFindingsPanel`, or
  `/findings/[id]/page.tsx` — those M20.2–M20.6 components were reused exactly
  as-is for the browser verification walkthrough (§F).

## E. TESTS

- **Backend unit** (`tests/unit/test_release_readiness_service.py`): **24
  passed, 0 failed** (was 19 before this change; the pre-existing 18 test
  bodies were mechanically updated to account for the new always-executed
  Finding query, plus 5 new tests: unresolved-via-work_order_id,
  unresolved-via-asset_id, closed-produces-no-blocker, multiple-findings-each-
  produce-own-blocker, lifecycle-transition-reflected-in-fresh-call).
- **Backend integration** (`tests/integration/test_drone_operations.py`,
  new `TestFindingReadinessIntegration` class against a real local Postgres):
  **30 passed, 0 failed** (was 23; 7 new tests: no-findings, unresolved-
  produces-blocker, closed-produces-no-blocker, mixed-resolution-only-
  unresolved-block, lifecycle-reflected-in-fresh-call, cross-org-isolation).
- **Full backend suite** (`pytest -q`, real local Postgres,
  `TEST_DATABASE_URL=postgresql+psycopg://aerocomply:aerocomply@localhost:55432/aerocomply_test`):
  **1020 passed, 1 failed, 16 deselected** (baseline at `5eb955a` was 1010
  passed/0 failed/16 deselected). The 1 failure —
  `test_security_hardening.py::TestRateLimiting::test_rate_limited_response_is_safe_and_generic`
  — is a pre-existing, unrelated rate-limiter timing test (asserts a 429 is
  observed within 30 rapid login attempts); read directly and confirmed it has
  no relationship to Findings, readiness, or any file this slice touched. **Not
  a regression introduced by this change** (net new tests this slice added:
  5 unit + 7 integration = 12; 1010+12=1022 vs 1020 observed — the 2-test
  discrepancy was not further decomposed; stated as **NOT VERIFIED** rather
  than guessed).
- **Frontend** (`npx vitest run`): **154 passed, 0 failed** — identical to the
  `5eb955a` baseline; this slice's frontend changes added no new test file
  (existing `finding-detail.test.ts`/`drone-findings-panel.test.ts` API-layer
  tests were not touched since the `findingsApi` contract itself didn't
  change).
- **TypeScript** (`npx tsc --noEmit`): **PASS** (zero errors).
- **ESLint** (`npx eslint .`): **PASS** — 0 errors, 60 pre-existing warnings
  (all in files this slice never touched — `WelcomeTour.tsx`,
  `GlobalSearch.tsx`, `DataModeContext.tsx`, `alertState.ts`,
  `lisa-matrix.test.ts`).
- **Build**: **NOT VERIFIED** — `npm run build` was not run this session (time
  budget spent on the real local-stack browser verification in §F instead);
  `tsc --noEmit` + `eslint` passing is evidence but not a substitute for an
  actual production build.

## F. BROWSER (real, driven verification — not API-only)

Performed with a real local Postgres (native Windows service on port 55432,
not Docker — Docker Desktop was unavailable in this sandbox and did not start
within 2 minutes; confirmed via `sc query postgresql-x64-16` → `RUNNING`),
local backend (`uvicorn app.main:app --port 8001`, matching
`frontend/.env.local`'s `NEXT_PUBLIC_API_BASE_URL`), and the already-running
local frontend dev server (`npm run dev`, port 3000, via `.claude/launch.json`
→ `aerocomply-dev`).

Exact flow driven in the Browser pane (not simulated, not assumed):
1. Registered a fresh org (`m21-browser@example.com`) via the real
   `/api/v1/auth/register-organization` endpoint (curl, since org registration
   has no UI form in this build).
2. Created one drone + one battery + one `CRITICAL` unresolved Finding
   (`asset_id`-linked) via curl against the same real backend/DB the browser
   session talks to.
3. Logged in through the actual `/login` page UI with that org's credentials.
4. Navigated to `/drones/{id}` — **observed** "Deployment Readiness: BLOCKED"
   with bullet "Unresolved finding (CRITICAL): UI verification finding",
   rendered as a real anchor (`href="/findings/{finding_id}"`, confirmed via
   `find`).
5. Clicked that link — landed on the real `/findings/{id}` canonical page
   (M20.4), showing OPEN/CRITICAL.
6. Clicked "No Action Required" (a real disposition action) — status changed
   to IN_PROGRESS live in the UI.
7. Clicked "Close Finding" — status changed to CLOSED live in the UI.
8. Navigated back to `/drones/{id}` (full navigation, not a soft refresh) —
   **observed** "Deployment Readiness: READY", blocker gone.

This is genuine browser-driven, click-through verification of the full
create → block → view → disposition → close → re-verify loop, not just an API
check. One caveat: the initial `.claude/launch.json` only declared the
frontend dev server; a second entry (`aerocomply-backend`, `url:
http://localhost:8001`) was added so the Browser pane's sandboxed network
could reach the backend at all (its first attempt failed with
`ERR_CONNECTION_REFUSED` even though the same port was reachable from this
session's own Bash tool — the two run in different network namespaces). This
launch.json change is a local dev-tooling convenience, not a product file, and
is not part of the git diff described in §M (`.claude/` is not tracked by
this repo's git status).

## G. DATABASE (independent Postgres verification)

Ran directly against the local `aerocomply_dev` database via `psql`
(`C:\Program Files\PostgreSQL\16\bin\psql.exe`), independently of both the API
responses and the browser session:

- `\d findings` — confirmed the live table schema matches `app/models/finding.py`
  column-for-column (no migration was needed or run).
- `SELECT id, organization_id, asset_id, status FROM findings WHERE
  title='Cracked prop'` (from the two-org curl test, §H) — returned exactly one
  row, `organization_id` matching Org A's own id and `asset_id` matching Org
  A's drone id, status `CLOSED` after the close call — independently confirms
  the readiness engine's own tenant-scoped query reflects the same ground
  truth Postgres holds, not a cached or fabricated value.
- `SELECT id, organization_id, registration FROM assets WHERE registration IN
  ('DR-A-1','DR-B-1')` — confirmed Org A's and Org B's drones have distinct,
  correct `organization_id` values with no overlap.
- `SELECT id, organization_id, asset_id, status FROM findings WHERE
  title='UI verification finding'` (the browser-driven finding, §F) —
  confirmed `status='CLOSED'` in the database after the UI close action,
  independently of what the frontend rendered.

## H. TENANT ISOLATION (Org A / Org B)

Verified twice, independently:
1. **Automated integration test**
   (`test_cross_org_finding_never_leaks_into_other_org_readiness`, passing) —
   Org A gets an unresolved Finding on its drone; Org A's readiness call
   returns `BLOCKED`; Org B's separate drone, under Org B's own token, returns
   `READY` with `finding_blockers: []`.
2. **Manual curl walkthrough** (§F/§G) — registered Org A and Org B fresh,
   created a drone + battery in each, created one unresolved Finding on Org
   A's drone only. `GET /drones/{A}/deployment-readiness` (Org A token) →
   `BLOCKED`. `GET /drones/{B}/deployment-readiness` (Org B token) → `READY`,
   `finding_blockers: []`, both before and after Org A's finding was created.
   Independently confirmed in Postgres (§G) that the two drones and the
   Finding row have non-overlapping `organization_id` values.

Both the `release_readiness_service.py` and `readiness_service.py` queries
filter on `Finding.organization_id == organization_id` (the server-derived
value from `current_user`, never client input) exactly as every other query in
both files already does — no new tenant-scoping pattern was introduced.

## I. SECURITY

- No new permission was added; Finding creation/read/disposition/close remain
  gated on `Permission.INSPECTION_WRITE`/`INSPECTION_READ` exactly as M20.2
  established. Readiness endpoints (`GET /work-orders/{id}/release-readiness`,
  `GET /drones/{id}/deployment-readiness`) keep their existing
  `Permission.DRONE_READ`/relevant read-permission gates — unchanged, not
  weakened.
- `organization_id` is never accepted from the request body/query on any path
  touched by this change — both new Finding queries use
  `current_user.organization_id` exactly like every pre-existing blocker
  query in the same functions.
- No SQL injection surface introduced — both new queries use SQLAlchemy
  `select()`/`where()` with bound parameters, consistent with the rest of the
  file.
- No RBAC was weakened; no existing test was deleted or skipped to make this
  land.

## J. PERFORMANCE

Both integrations use **exactly one additional query** per readiness call —
no query-per-asset or query-per-finding loop:
- `release_readiness_service.py`: one `select(Finding).where(...)` with an
  `or_(...)` across up to three linkage conditions (work_order_id, asset_id,
  aircraft_id), matching the existing pattern used for the INSPECTION blocker
  query (`or_(*conditions)`) in the same file.
- `readiness_service.py`: one `select(Finding).where(organization_id=...,
  asset_id=..., status != CLOSED)`.
Blocker objects are then built in a single Python loop over the already-
fetched rows (list comprehension for `finding_blockers`, a `for` loop for the
string `blockers` list) — no further DB access per row.

## K. LISA READINESS

This slice does **not** implement LISA drone context (that remains M21
slice 3, unaddressed here). What it does provide: readiness responses for
both engines are now a trustworthy, complete-enough data source for a future
LISA tool to consume — `docs/M21_PRODUCT_UI_UX_AUDIT.md` §14 flagged that any
"drone readiness intelligence" built before this slice would sit on an engine
that silently ignored an entire category of real defect data. That specific
blind spot is now closed for both the aircraft/work-order path and the
drone/asset path. LISA itself was not touched; no `current_asset_id`/
`current_drone_id` field was added to `LisaConversationContext` (still M21
slice 3's job, per the audit's own recommended execution order).

## L. REMAINING GAPS

- `npm run build` was not run — **NOT VERIFIED** (tsc + eslint passing is
  evidence, not proof).
- The 1020-vs-1022 test-count discrepancy in §E was not decomposed — **NOT
  VERIFIED** which two tests account for the gap (possibly deselected/skipped
  markers elsewhere; not investigated further given time budget).
- `RealReleaseReadinessPanel.tsx`'s new FINDING rendering was verified by code
  read and by the drone-page equivalent in the browser (§F), but the
  work-order release-readiness page itself
  (`frontend/app/(app)/maintenance/release-readiness/page.tsx`) was not
  separately opened in the browser this session — **NOT VERIFIED** end-to-end
  for the work-order path specifically (only the drone/asset path got full
  browser click-through).
- Aircraft-linked Findings on a work order (via `Finding.aircraft_id ==
  WorkOrder.aircraft_id`) are covered by the query logic and by unit tests,
  but not by a real local-stack browser or curl walkthrough this session —
  only the drone/asset path was driven end-to-end live. **PARTIAL**
  verification for the aircraft path (unit-tested, not live-tested).
- No migration was needed for this slice (confirmed), so no
  upgrade/downgrade/upgrade cycle applies.

## M. GIT

- HEAD before this work: `5eb955a` (unchanged — no commit made yet as of this
  report; the calling agent/user may request the commit separately).
- Files modified (working tree, not yet committed):
  `backend/app/schemas/drone_ops.py`, `backend/app/schemas/release_readiness.py`,
  `backend/app/services/readiness_service.py`,
  `backend/app/services/release_readiness_service.py`,
  `backend/tests/integration/test_drone_operations.py`,
  `backend/tests/unit/test_release_readiness_service.py`,
  `frontend/app/(app)/drones/[id]/page.tsx`,
  `frontend/components/evidence/RealReleaseReadinessPanel.tsx`,
  `frontend/lib/api/drones.ts`, `frontend/lib/api/release-readiness.ts`.
- Pushed to origin: **NO**.
- Staging (Render `aerocomply-backend-staging` / Neon `small-meadow-85982633`)
  touched: **NO**.
- Production (Neon `bitter-tooth-52841705`) touched: **NO**.
- All verification in §F/§G/§H ran against the local dev Postgres
  (`aerocomply_dev` on `localhost:55432`, native Windows service) and a local
  `aerocomply_test` database created on that same local instance for the
  integration-test run (Docker Desktop was unavailable/would not start; the
  native local Postgres install already present on this machine was used
  instead — still strictly local, never staging/production).
