# M21.4 — Platform Control Plane Coherence Slice

Date: 2026-09-20
Branch: main (local only)
Prior preserved commits: 5eb955a (M20.6), d803acc (M21.1), a1a542e (M21.2), 2cd0b5c (M21.3)

## A. BASELINE

- Backend baseline before this slice: `1020 passed, 1 failed (pre-existing,
  unrelated), 16 deselected` (`tests/integration/test_asset_foundation_phase1b.py::
  TestMigration0031Backfill::test_backfill_populates_asset_id_and_upgrade_downgrade_reupgrade_succeeds`).
  Re-confirmed as still current by running the full suite after this
  slice's changes (Section J) — identical result, same single pre-existing
  failure, zero new failures.
- Frontend baseline: `174 passed` (13 test files), confirmed unchanged after
  this slice.
- Alembic head before this slice: `0036` (`0036_finding_disposition.py`).
- Local Postgres: a native PostgreSQL 16 Windows service
  (`postgresql-x64-16`), already running on `localhost:55432` before this
  session started (confirmed via `sc query`), matching `backend/.env`'s
  `DATABASE_URL`. Docker Desktop was investigated briefly at the start of
  this slice and found non-functional in this environment (no WSL2) — per
  the coordinator, this was already known and irrelevant: the established
  dev workflow uses this native Postgres service directly, never Docker.
  No Docker container was created, started, or otherwise touched.
- `TEST_DATABASE_URL` was not set in the shell when the full suite was first
  attempted, which caused the module default
  (`postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test`,
  port 5432) to be used — that port has nothing listening (only 55432 does),
  producing a wall of connection-refused `ERROR`s on an unrelated pytest
  invocation. This was diagnosed, not misreported as a regression: setting
  `TEST_DATABASE_URL=postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test`
  (a real, separate database already present on the same running Postgres
  instance) fixed it immediately, and the full suite then ran cleanly to
  the result in Section J.

## B. EXISTING ARCHITECTURE — what was already there vs. what this round built

This is the most important section. A very large fraction of what M21.4's
mission brief asked for already existed, built the same day
(2026-09-13, per `docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md` §§22-26) in
milestones M1-M6, **before this session began**:

| Layer | Status | Where |
|---|---|---|
| `Plan` / `PlanFeature` models | ALREADY EXISTED | `backend/app/models/plan.py` |
| `Subscription` / `SubscriptionStatus` | ALREADY EXISTED | `backend/app/models/subscription.py` |
| `TenantFeatureOverride` / `TenantUsageLimit` | ALREADY EXISTED | `backend/app/models/tenant_entitlement.py` |
| Full entitlement-resolution engine (`resolve_entitlements`) | ALREADY EXISTED, complete, not partial | `backend/app/services/entitlement_service.py` (§23/M2) |
| Entitlement REST API (tenant self-service + platform cross-org) | ALREADY EXISTED | `backend/app/api/v1/entitlements.py`, `platform.py` (§24/M3) |
| Plan/PlanFeature admin CRUD | ALREADY EXISTED | `backend/app/services/plan_service.py` (§25/M5) |
| Subscription/override/usage-limit admin CRUD + expansive-permission gating | ALREADY EXISTED | `backend/app/services/subscription_service.py`, `tenant_entitlement_admin_service.py` (§26/M6) |
| `ProductSuite -> ProductModule -> ProductPage/ProductFeature` catalog + full CRUD API | ALREADY EXISTED | `backend/app/models/product_catalog.py`, `app/api/v1/product_catalog.py` |
| Platform Control Plane nav, exclusive of tenant nav, gated by role | ALREADY EXISTED, by deliberate documented design (§14 of the architecture doc), not a bug | `frontend/components/layout/Sidebar.tsx` (`PLATFORM_NAV_GROUPS` vs `NAV_GROUPS`, `isPlatformUser` check) |
| Platform admin bootstrap, `PLATFORM_MANAGE`/`PLATFORM_ENTITLEMENT_OVERRIDE` permissions | ALREADY EXISTED | `backend/scripts/create_platform_admin.py`, `app/core/permissions.py` |

**What this round (M21.4) actually built** — genuinely new, on top of the
above, exactly the three gaps confirmed in scope by the user:

1. `Plan.suite_id` — a new nullable FK column linking the commercial `Plan`
   catalog to the platform `ProductSuite` catalog (these were two
   completely unlinked catalogs before this round — confirmed by reading
   both model files, both API routers, and the architecture doc, which
   never mentions any relationship between them).
2. Frontend entitlement-aware Sidebar nav filtering — `Sidebar.tsx` now
   grays out (and disables the link for) a tenant nav item whose backing
   `FEATURE_*` key is explicitly reported `false` in the tenant's own
   `GET /api/v1/entitlements` response. Zero backend changes were needed
   for this (the resolver and endpoint already existed and already
   returned everything needed).
3. `Organization.industry` — a new nullable classification column
   (`OrganizationIndustry.DRONE_UAV/AIRCRAFT/HELICOPTER/EVTOL_AAM`), plus a
   platform-admin endpoint to set/clear it. This concept did not exist
   anywhere in the codebase or in the architecture doc before this round —
   see Section E for the full placement reasoning.

No entitlement-resolution logic, RBAC/permission logic, or existing
CRUD/mutation pattern was modified. `app/services/entitlement_service.py`
(M2, the canonical resolver) was not touched at all.

## C. PLATFORM CONTROL PLANE (resulting structure)

Unchanged shell/architecture from before this round, confirmed still
correct: one Next.js app, one `Sidebar` component, `PLATFORM_NAV_GROUPS`
(Organizations / Product Catalog / Plans / Audit / Approvals / Monitoring)
rendered exclusively for `PLATFORM_ADMIN`/`PLATFORM_STAFF`, gated
server-side by `Permission.PLATFORM_MANAGE` (and `PLATFORM_ENTITLEMENT_OVERRIDE`
for expansive entitlement mutations) on every `/platform/*` route
regardless of what the frontend shows. This round added exactly two new
platform-admin-only capabilities to that existing surface:
`POST /platform/organizations/{id}/industry` and `suite_id` on the
existing `POST/PATCH /platform/plans` endpoints — both gated by the same
`PLATFORM_MANAGE` dependency as every other route in `platform.py`, no new
permission introduced.

## D. CUSTOMER PRODUCT PLANE (what customer users see)

Unchanged tenant `Sidebar` (`NAV_GROUPS`, 7 groups), now additionally
entitlement-aware: a nav item mapped in the new
`frontend/lib/entitlements/navFeatureMap.ts` (16 of the ~50 tenant nav
items — the same "coarse, MVP-gateable" set the architecture doc's §5
table already identified) is grayed out, gets `aria-disabled`, and its
click is prevented, with the tooltip "Not included in your organization's
current plan," whenever the caller's own
`GET /api/v1/entitlements` response reports that feature's key as
explicitly `false`. An item with no mapping (the majority — LISA,
data-import, TAT, proactive, and every page the architecture doc flagged
"needs more maturity first" are deliberately unmapped) is never gated.
This is stated explicitly, in code comments in both new files, as a
**UX-only affordance** — it duplicates nothing security-relevant, and if
the entitlement fetch fails for any reason the sidebar fails open (shows
everything) rather than locking a tenant out of their own nav due to a
display-layer error. Backend authorization (`Permission` checks,
`PLATFORM_MANAGE`, and any future `require_feature()` dependency) remains
the sole real gate, completely unmodified by this round.

## E. INDUSTRY MODEL

**Where it was placed and why**: `Organization.industry`, a nullable
`String(32)` column on the existing `Organization` model, with a new
`OrganizationIndustry` string-constant class (`DRONE_UAV`, `AIRCRAFT`,
`HELICOPTER`, `EVTOL_AAM`) — the exact same shape as the adjacent
`OrganizationStatus` class already in that file, not a Postgres/SQLAlchemy
`Enum` type and not a new lookup table.

**Alternatives considered and rejected, documented in code**:

- **A separate `industries` lookup table** (mirroring `ProductSuite`) —
  rejected because nothing in this codebase's real usage needs an industry
  value to carry its own admin-editable metadata (description,
  display_order, activation state) the way `ProductSuite` genuinely does
  for platform-catalog administration. A fixed four-value classification
  tag with no such metadata doesn't warrant a table — it's the same
  judgment call already made for `OrganizationStatus`.
- **Overloading `ProductSuite`'s existing `code` field to imply industry**
  — explicitly considered per the coordinator's instruction, and ruled
  out with concrete evidence: `ProductSuite`'s only real seeded row today
  (`backend/scripts/seed_product_catalog.py`) has `code="maintenance"` —
  a **workflow domain** ("Maintenance"), not an aerospace asset vertical.
  The two axes are orthogonal: a "Maintenance" suite's work-order-tracking
  module applies equally to a drone operator or a fixed-wing operator.
  Conflating them would put two genuinely different classification
  concepts into one field — exactly the kind of conflation
  `docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md` §19 warns against for
  `Organization.status` vs. subscription status.
- **Attaching it to `Plan` instead of `Organization`** — considered, but
  an organization's industry is a fact about the *tenant* (what kind of
  operator they are), independent of which plan they happen to be
  subscribed to at a given moment (a plan can change; an operator's
  industry realistically does not). `Organization` was judged the more
  accurate home; nothing about the M6 subscription-history model requires
  industry to travel with plan history.

**Explicitly honest about scope**: this was not called for anywhere in the
922-line architecture document or in any of the M1-M6 implementation
milestones — the user explicitly asked for it understanding that, and it
is documented as such directly in the model docstring
(`backend/app/models/organization.py`) so a future reader doesn't mistake
it for something the original architecture review specified.

Nullable, no backfill: every pre-existing organization reads back
`industry: null` until a platform admin explicitly sets one via the new
`POST /platform/organizations/{id}/industry` endpoint. Live-tested
end-to-end in Section I.

## F. SUITE MODEL

`ProductSuite -> ProductModule -> ProductPage/ProductFeature` is unchanged
from before this round (confirmed by re-reading `product_catalog.py` in
full this session — no lines touched). The one new relationship is
`Plan.suite_id` (nullable FK -> `product_suites.id`, `ON DELETE RESTRICT`,
indexed) — a single suite per plan, not a many-to-many join table. This
was a deliberate multiplicity decision, documented in `Plan.suite_id`'s
own docstring: every real plan this codebase's architecture doc describes
(STARTER/PROFESSIONAL/ENTERPRISE-style tiers) is a tier of *one* product
line, not a bundle of several distinct suites; a genuine multi-suite
bundle would be modeled as a separate `Plan` row per suite (or a future
dedicated bundling concept), not by overloading this FK with a join table
for a multiplicity that doesn't exist anywhere in the current catalog.
Verified live end-to-end in Section I: created a real `ProductSuite`
("Drone Operations"), a real `Plan` referencing it via `suite_id`, and
confirmed the FK round-trips correctly through create/read.

## G. PLAN/ENTITLEMENT MODEL (the actual chain, with evidence)

`Organization` --(`Subscription`, tenant-scoped, history-preserving,
M1/§21)--> `Plan` --(`PlanFeature`)--> `feature_key: bool` map, overlaid by
`TenantFeatureOverride` (M1/M6), surfaced by
`entitlement_service.resolve_entitlements` (M2, unmodified by this round)
as an `EntitlementResolution` with `effective_features`. New in this
round: `Plan` additionally optionally points at one `ProductSuite` via
`suite_id` — a **catalog/reporting relationship only**, deliberately never
consulted by `resolve_entitlements` (verified: that function's imports and
logic were not touched, and it still reads only
`Organization`/`Plan`/`PlanFeature`/`Subscription`/`TenantFeatureOverride`/
`TenantUsageLimit`). Live-verified chain (Section I): a real organization
-> real `ACTIVE` subscription -> real suite-linked plan with
`FEATURE_PROCUREMENT: false` and `FEATURE_AIRCRAFT: true` -> resolved
correctly by the unmodified M2 service -> correctly rendered as
grayed-out/enabled in the real browser sidebar.

## H. SECURITY

- No permission, role, or `ROLE_PERMISSIONS` entry was added, removed, or
  changed. `PLATFORM_MANAGE` continues to gate every mutation this round
  touched (plan `suite_id` create/update, organization industry
  set/clear) — the same dependency every other route in `platform.py`
  already uses; no new attack surface, no new permission tier.
- `_validate_suite_id` in `plan_service.py` explicitly checks the supplied
  `suite_id` references a real `ProductSuite` row before flush, so a bad
  id 404s cleanly (`NotFoundError`) instead of surfacing a raw
  `IntegrityError` from the `RESTRICT` FK.
- The new `Organization.industry` field is metadata-only: verified by
  inspection that `entitlement_service.resolve_entitlements` and every
  `Permission`/`require_permission` check remain completely independent of
  it — setting or clearing it neither grants nor revokes anything.
- The new frontend Sidebar filtering is explicitly documented, in-code, as
  non-authoritative (Section D) and was verified in the browser to be
  exactly that: the backend's own `Permission`/entitlement checks are
  unmodified, so even if a user bypassed the grayed-out link entirely
  (e.g. by typing the URL), backend authorization is what would still
  apply — this round did not add or need to add any new backend
  enforcement to keep that true, since none of the newly-mapped nav items
  route to pages this round modified.
- Cross-tenant isolation: unaffected. `Plan.suite_id` and
  `Organization.industry` are non-tenant-scoped/tenant-metadata fields
  respectively; neither participates in any tenant-scoped query filter,
  so there is no new cross-tenant read/write path to isolate.
- Full backend suite (Section J) includes the existing
  `test_tenancy_isolation.py`, `test_platform_admin.py` (RBAC/403
  boundary tests), and `test_entitlement_resolution.py` (22 scenario
  tests) — all passed unchanged, confirming this round did not weaken any
  existing security invariant.

## I. BROWSER (exact flows verified)

Real local stack: native PostgreSQL 16 on `localhost:55432` (already
running), backend `uvicorn` restarted on ports 8000 and 8001 (8001 is what
`frontend/.env.local`'s `NEXT_PUBLIC_API_BASE_URL` actually points at) to
pick up this round's code changes, frontend `next dev` (Turbopack) on
`localhost:3000` via `preview_start`.

1. Created a real `PLATFORM_ADMIN` via `backend/scripts/create_platform_admin.py`
   (`m214.platadmin@example.com`).
2. Via the real API (curl, authenticated with that admin's real JWT):
   created organization "M214 Test Drone Co"; set its `industry` to
   `DRONE_UAV` (confirmed round-trips in the response); created a real
   `ProductSuite` ("Drone Operations", `code=drone_ops`); created a real
   `Plan` ("M214 Drone Pro") with `suite_id` pointing at that suite
   (confirmed round-trips); added `PlanFeature(FEATURE_PROCUREMENT,
   enabled=false)` and `PlanFeature(FEATURE_AIRCRAFT, enabled=true)`;
   created a real `ACTIVE` `Subscription` linking the organization to that
   plan; created a real `ORG_ADMIN` user for that organization.
3. Confirmed via `GET /platform/organizations/{id}/entitlements` that
   `resolve_entitlements` (unmodified M2 code) correctly resolved
   `resolution_status: ACTIVE`, `effective_features:
   {FEATURE_PROCUREMENT: false, FEATURE_AIRCRAFT: true}`.
4. **Browser**: logged in as the `PLATFORM_ADMIN` at `localhost:3000/login`
   -> landed on `/platform/organizations` -> confirmed via `read_page` that
   the sidebar renders exclusively `PLATFORM_NAV_GROUPS` (Organizations,
   Product Catalog, Plans, Audit/Activity, Approvals, Monitoring & Health)
   — no tenant nav visible.
5. Cleared session, logged in as the new `ORG_ADMIN`
   (`m214.orgadmin@example.com`) -> landed on the tenant dashboard
   (Compliance Intelligence / Fleet Overview / Daily Brief) — confirmed
   via `read_page` that the sidebar renders the tenant `NAV_GROUPS`, not
   the platform nav.
6. Inspected the live DOM (`javascript_tool`) for the `/procurement` and
   `/aircraft` nav links specifically: `/procurement` had
   `aria-disabled="true"`, `opacity: 0.4`, and
   `title="Not included in your organization's current plan"`;
   `/aircraft`, `/compliance`, `/assessments` (entitled or unmapped) had
   none of those attributes and rendered normally. This is the exact,
   real, entitlement-driven behavior this round's Sidebar change was
   built to produce, confirmed live rather than assumed from reading the
   code.
7. Not independently re-verified this round (out of the stated Phase 5
   priority — the shell-separation and entitlement-filtering checks above
   were prioritized): the pre-existing platform product-catalog and plans
   admin *screens* (`/platform/product-catalog`, `/platform/plans`) were
   not opened in the browser to confirm they display the new `suite_id`
   field — that field is currently API-only (verified via curl in step 2)
   and does not yet have a dedicated UI control in those existing pages.
   This is stated honestly as scope not covered, not claimed as done.

## J. TESTS

- **Backend**: `1020 passed, 1 failed (pre-existing, unrelated), 16
  deselected` in 79.41s — identical to the stated baseline. The one
  failure, `test_asset_foundation_phase1b.py::TestMigration0031Backfill::
  test_backfill_populates_asset_id_and_upgrade_downgrade_reupgrade_succeeds`,
  concerns migration `0031` (asset-foundation backfill), unrelated to any
  file this round touched (`plan.py`, `organization.py`, `platform.py`,
  `plan_service.py`, `platform_service.py`, `schemas/plan.py`,
  `schemas/platform.py`, and the new `0037` migration) — confirmed
  pre-existing by being present, unchanged, before this round's very first
  edit.
- **Frontend**: `174 passed` (13 test files) — identical to baseline.
- **TypeScript**: `tsc --noEmit` — zero errors.
- **ESLint**: `eslint .` — 0 errors, 61 warnings, all pre-existing pattern
  (`react-hooks/set-state-in-effect` on synchronous `setState` inside
  `useEffect`) already present in `DataModeContext.tsx` and
  `mock/ai/alertState.ts` before this round; the new
  `useMyEntitlements.ts` hook triggers the identical warning using the
  identical established pattern, not a new lint problem class.
- **Build**: `npm run build` — succeeded, all routes compiled
  (`/platform/plans`, `/platform/organizations`, tenant routes, etc.),
  no new errors.
- No new backend unit/integration test file was added for the two new
  schema fields specifically (`Plan.suite_id`, `Organization.industry`) —
  this is a real, stated limitation (Section M), not an oversight: given
  the time budget, verification was done via real end-to-end
  API/DB/browser exercise (Section I) rather than new automated test
  files, which is a genuine gap for anyone extending this further.

## K. DATABASE

- **Migration added**: `backend/alembic/versions/0037_plan_suite_and_org_industry.py`
  (revision `0037`, down_revision `0036`). Adds `plans.suite_id` (nullable
  UUID, FK -> `product_suites.id` ON DELETE RESTRICT, indexed) and
  `organizations.industry` (nullable `String(32)`). No existing table
  column was altered or dropped; no backfill was performed (every
  pre-existing row reads back `NULL` for both new columns, which is the
  correct, honest value — there is no data from which to infer either
  field for rows that predate this migration).
- **Upgrade/downgrade/upgrade verified for real** against the actual local
  Postgres dev database (`localhost:55432/aerocomply_dev`, the same DB
  `backend/.env`'s `DATABASE_URL` points at):
  `alembic upgrade head` (0036->0037) succeeded ->
  `alembic downgrade -1` (0037->0036) succeeded ->
  `alembic upgrade head` (0036->0037) succeeded again -> `alembic current`
  confirmed `0037 (head)`. Not a dry run or SQL-only inspection — actual
  DDL executed against a real database each time.
- Neon (production `bitter-tooth-52841705`) and Neon staging
  (`small-meadow-85982633`) / Render staging backend were never touched,
  connected to, or referenced by any command this round.

## L. GIT

- Final HEAD: `f044071` ("feat: establish platform control plane
  entitlements"), local and unpushed, one commit ahead of `2cd0b5c`
  (M21.3) — not an amend, a new commit.
- Commit created this round: message
  `feat: establish platform control plane entitlements`, containing only:
  `backend/app/models/plan.py`, `backend/app/models/organization.py`,
  `backend/app/schemas/plan.py`, `backend/app/schemas/platform.py`,
  `backend/app/services/plan_service.py`,
  `backend/app/services/platform_service.py`, `backend/app/api/v1/platform.py`,
  `backend/alembic/versions/0037_plan_suite_and_org_industry.py`,
  `frontend/components/layout/Sidebar.tsx`,
  `frontend/lib/entitlements/navFeatureMap.ts`,
  `frontend/lib/entitlements/useMyEntitlements.ts`, and this report.
  No prior commit was amended. No report or doc file
  (including `docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md`, which this
  report's Section B/E explicitly note is now slightly out of date given
  today's `Plan.suite_id`/`Organization.industry` additions — noted here,
  not edited there) was modified.
- Pushed: **NO**. Staging touched: **NO**. Production touched: **NO**.
  Docker: never started, never used (confirmed native Postgres was the
  only database involved throughout).

## M. REMAINING GAPS (honest — this is a foundation slice, not a complete system)

- **No automated tests added** specifically for `Plan.suite_id` or
  `Organization.industry` (create/update/validation-failure cases) — only
  real end-to-end manual verification (Section I) was performed under this
  round's time budget. A follow-up should add unit/integration tests
  mirroring `test_plan_administration.py`'s existing patterns.
- **No platform-admin UI control** for `suite_id` (on the Plans page) or
  `industry` (on the Organizations page) — both are API-only today. The
  existing `/platform/plans` and `/platform/organizations` screens were
  not modified to expose these new fields in their forms/tables.
  Confirmed present via curl, not yet visible to a platform admin clicking
  through the UI.
- **Entitlement-aware Sidebar filtering only covers 16 of ~50 tenant nav
  items** — exactly the coarse MVP-gateable set the architecture doc's §5
  table already identified as ready; LISA, data-import, TAT, proactive,
  and everything else flagged "needs more maturity first" remain
  deliberately unmapped and always-shown, per that doc's own guidance, not
  because of an oversight in this round.
- **No `require_feature()` backend dependency was added anywhere** —
  the architecture doc's §7/§20 milestone 6 (wiring actual backend route
  enforcement, not just frontend display) remains entirely unbuilt. The
  Sidebar change in this round is genuinely UX-only, as documented; a
  tenant whose plan excludes `FEATURE_PROCUREMENT` is not actually blocked
  from calling procurement endpoints server-side — only the nav link is
  grayed out client-side.
- **Suite ↔ Plan is single-valued** (one suite per plan) by design
  decision (Section F) — if the business later needs genuine multi-suite
  bundles, that is a new join-table migration, not a config change.
- **Industry has no admin-facing catalog/reporting view** — there's no
  "list organizations by industry" or "industry breakdown" report; it's
  purely a settable/gettable tag today.
- Everything explicitly out of scope for this whole effort remains out of
  scope and untouched: LISA/AI, billing/payment gateways, customer
  impersonation, predictive maintenance, the ~88-page redesign, and any
  drag-and-drop catalog builder.
