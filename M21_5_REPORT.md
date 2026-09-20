# M21.5 — Centralized Backend Entitlement Enforcement at the API Boundary

Date: 2026-09-20
Branch: main (local only)
Prior HEAD: d3efd70 (M21.4)

## A. BASELINE

- Backend baseline before this slice: `1020 passed, 1 failed (pre-existing,
  unrelated), 16 deselected` — the same pre-existing failure M21.4 reported
  (`test_asset_foundation_phase1b.py::TestMigration0031Backfill::
  test_backfill_populates_asset_id_and_upgrade_downgrade_reupgrade_succeeds`),
  concerning migration `0031`, unrelated to anything this slice touches.
- Local Postgres: native PostgreSQL 16 Windows service on
  `localhost:55432`, already running (same instance M21.4 used). Two real
  databases on it were used: `aerocomply_dev` (real end-to-end
  API/DB verification, Section G) and `aerocomply_test` (automated suite,
  `TEST_DATABASE_URL`).
- Backend started for real verification: `uvicorn app.main:app --port
  8010` against `aerocomply_dev`.
- Neon (production `bitter-tooth-52841705`) and Neon staging
  (`small-meadow-85982633`) / Render staging were never touched, connected
  to, or referenced.

## B. EXISTING ENTITLEMENT ARCHITECTURE (confirmed reused, cited)

The mission brief assumed `require_feature()` did not exist yet
("M21.4 explicitly deferred" it). That assumption was **wrong** — auditing
`backend/app/core/deps.py` in full found it already built, in a much
earlier milestone than M21.4:

- `resolve_entitlements()` — `backend/app/services/entitlement_service.py:138-309`.
  Reused **verbatim**, zero changes. This slice never imports, edits, or
  re-implements any part of it.
- `require_feature(feature_key: str)` — `backend/app/core/deps.py:104-140`,
  added in commit `8cc3707` ("M17.3: establish billing and entitlement
  foundation"), confirmed via `git log -p` on `deps.py`. It already: calls
  `resolve_entitlements(db, organization_id=current_user.organization_id)`
  (line 133), grants only when `resolution_status` is `ACTIVE` or
  `INACTIVE_PLAN` and `effective_features[feature_key]` is `True` (lines
  121-136), and raises `ForbiddenError` (reusing
  `backend/app/core/errors.py`'s existing exception type, `code="forbidden"`,
  HTTP 403) otherwise.
- `backend/tests/integration/test_require_feature_dependency.py` (also
  M17.3) already unit-tests the dependency's inner logic directly
  (11 pre-existing tests: grant/deny/no-subscription/suspended/unknown-key,
  plus a permission×entitlement logical matrix and one tenant-isolation
  case) — confirmed still passing, unmodified.

**What M17.3 built but never wired anywhere**: `require_feature` existed as
a dependency factory with zero real callers. `grep -rn require_feature
backend/app/api/` before this slice returned no matches — no route in the
entire API surface used it. This is the exact, genuine gap M21.4's report
(Section M) correctly flagged: *"No `require_feature()` backend dependency
was added anywhere... a tenant whose plan excludes a feature is not
actually blocked from calling the endpoints server-side."* That gap is what
this slice closes — not building a new mechanism, but mounting the
already-built, already-tested one onto real routes for the first time.

## C. CENTRAL ENFORCEMENT DESIGN

No new code was added to `app/core/deps.py` or `app/core/errors.py` — the
existing `require_feature()` factory and existing `ForbiddenError`
(`code="forbidden"`) were sufficient and are used exactly as designed. The
"central mechanism" this slice's mission asked for already existed; this
slice's actual work was Sections D-G below: selecting 3 real features,
extending the product catalog with real entries for 2 of them, mounting
`Depends(require_feature(...))` alongside the existing
`Depends(require_permission(...))` on 6 real GET endpoints, and proving it
end-to-end.

Composition pattern applied identically on all 6 endpoints (matches
`deps.py:94-98`'s own documented convention):

```python
@router.get(...)
def handler(
    ...,
    current_user: CurrentUser = Depends(require_permission(Permission.X)),
    _entitled: CurrentUser = Depends(require_feature("feature_key")),
) -> ...:
```

`require_permission` always ordered first (matches the architecture doc's
§7 ordering rule), so a caller lacking RBAC gets the RBAC error, never an
entitlement error that would leak plan information to an unauthorized
caller.

## D. THREE FEATURES PROTECTED

**Note on feature-key selection**: the platform's `ProductFeature` catalog
(`backend/scripts/seed_product_catalog.py`) had only **one** real seeded
feature before this slice — `work_order_management` (Maintenance suite,
backing `work_orders.py`). Drone and Procurement, though named in the
mission brief and backed by real, fully-built routers/services, had **no**
catalog entry yet. Per the mission's own instruction ("if those exact
three don't exist, pick 3 real ones that do, and justify the
substitution"), this slice extended `seed_product_catalog.py` with two more
real catalog entries — `drone_fleet_management` (Drone Operations suite,
backing `drones.py`) and `procurement_management` (Procurement suite,
backing `procurement.py`) — following the script's own documented
one-deliberate-entry-at-a-time convention, rather than substituting
different domains. All three are now real `ProductFeature` rows, seeded
into the real local `aerocomply_dev` database and confirmed via the
platform admin API (Section G).

| # | Feature | feature_key | Endpoints protected | RBAC (unchanged) |
|---|---|---|---|---|
| 1 | Work Order Management | `work_order_management` | `GET /api/v1/work-orders`, `GET /api/v1/work-orders/{id}` | `Permission.AIRCRAFT_READ` |
| 2 | Drone Fleet Management | `drone_fleet_management` | `GET /api/v1/drones`, `GET /api/v1/drones/{id}` | `Permission.DRONE_READ` |
| 3 | Procurement Management | `procurement_management` | `GET /api/v1/procurement-requests`, `GET /api/v1/procurement-requests/{id}` | `Permission.PROCUREMENT_READ` |

Per the mission's own risk guidance ("GET endpoints are the safest place to
prove the mechanism"), only GET (read) endpoints were gated; POST/PATCH/
approval-workflow endpoints on all three routers are untouched, so no
write-path regression risk was introduced.

Both entitlement and RBAC independently verified for each (real HTTP,
Section G):

- Entitled + authorized -> 200.
- Unentitled (no subscription, or plan with feature disabled) -> 403,
  `{"error":{"code":"forbidden","message":"Organization is not entitled to
  feature: <key>"}}` — distinct message from RBAC's
  `"Missing required permission: ..."`, though both currently share
  `code="forbidden"` (Section J notes this as a real, honest limitation).
- Authorized (RBAC) but unentitled -> still 403 (entitlement gate fires).
- Entitled but unauthorized (no role grant) -> still 403 (RBAC gate fires).

## E. SUBSCRIPTION/OVERRIDE BEHAVIOR (reused, not modified)

Reused exactly as `resolve_entitlements` already defines
(`entitlement_service.py`'s own module docstring, design decisions 1-3):

- `ACTIVE`/`TRIALING`/`PAST_DUE` subscriptions grant access;
  `CANCELED`/`SCHEDULED`/expired (`ends_at` in the past) do not.
- A `TenantFeatureOverride` row always wins over the plan default, in
  either direction (grant or revoke), **but only when a current
  subscription already exists** — confirmed live (Section G) that an org
  with **zero** subscription rows resolves to `NO_SUBSCRIPTION` with an
  empty feature map and is denied regardless of any override row, since
  `resolve_entitlements` never reaches its override-application step
  (Step 5) without first resolving a current subscription (Step 2). This is
  existing, correct, documented behavior — not something this slice
  changed — and was specifically re-derived here because the first override
  test attempt (grant to a subscription-less org) surfaced it as a real
  finding worth stating explicitly, not silently working around.
- A suspended organization is denied before entitlement is even evaluated
  (`get_current_user` returns 401 first) — confirmed live.

## F. SECURITY TESTS

`backend/tests/integration/test_feature_entitlement_enforcement.py` (new,
11 tests, all passing), driving real HTTP requests through the real
FastAPI app (unlike the pre-existing `test_require_feature_dependency.py`,
which calls the dependency's inner function directly):

| Scenario | Result |
|---|---|
| Entitled org succeeds on all 3 protected endpoints | PASS |
| No subscription -> 403 with `code="forbidden"` | PASS |
| Feature disabled on plan -> 403 | PASS |
| ORG_ADMIN (broad RBAC) still denied if unentitled | PASS |
| Entitled but roleless user denied for RBAC reason (entitled admin on same org succeeds, proving it's genuinely a different gate) | PASS |
| Tenant isolation: Org B's entitlement never satisfies Org A's check | PASS |
| TenantFeatureOverride grants a feature the plan excludes | PASS |
| TenantFeatureOverride revokes a feature the plan includes | PASS |
| Expired subscription (`ends_at` in the past) denies | PASS |
| Suspended organization denies (401, pre-entitlement) even with an otherwise-entitled plan | PASS |
| Platform admin route (`/platform/organizations`) succeeds regardless of subscription state (route never passes through `require_feature`) | PASS |

All 11 pass. Additionally re-verified live over real HTTP against the real
local dev database (Section G), not only against the test database.

## G. REAL VERIFICATION (Postgres + API, both real)

Real local stack: native PostgreSQL 16 (`localhost:55432/aerocomply_dev`),
backend `uvicorn` on port 8010 (started fresh to pick up this slice's code).

1. `alembic upgrade head` confirmed no-op (no new migration in this slice —
   see Section J for why none was needed).
2. `scripts/seed_product_catalog.py` run against `aerocomply_dev`: created
   3 suites/modules/pages/features (Maintenance/work_order_management
   pre-existing-shape, plus the 2 new Drone/Procurement entries).
3. `scripts/create_platform_admin.py` created a real `PLATFORM_ADMIN`
   (`m215.platadmin@example.com`).
4. Registered two real orgs via the real `/auth/register-organization` API:
   Org A (`0570d3be-...`), Org B (`ab7d36d7-...`).
5. Via the real platform admin API (real JWT): created Plan
   `m215-drone-plan` with `PlanFeature(drone_fleet_management, enabled=
   true)`, subscribed Org A to it (`ACTIVE`).
6. **Org A (entitled) `GET /api/v1/drones`** -> real HTTP 200.
7. **Org B (no subscription at all) `GET /api/v1/drones`** -> real HTTP
   403, body `{"error":{"code":"forbidden","message":"Organization is not
   entitled to feature: drone_fleet_management"}}` — the entitlement code,
   not RBAC's (Org B's `ORG_ADMIN` holds `DRONE_READ`, proving this is
   genuinely the entitlement gate, not RBAC, that fired).
8. **Platform admin `GET /api/v1/platform/organizations`** -> real HTTP
   200, unaffected by either org's subscription state (route never passes
   through `require_feature`).
9. **Override grant**: created a base Plan for Org B (no
   `drone_fleet_management`), subscribed Org B to it (`403` confirmed with
   subscription present, no override, feature disabled). Platform admin
   `POST .../feature-overrides` with `{"feature_key":
   "drone_fleet_management","enabled":true}` -> Org B's `GET /drones` then
   returned real HTTP 200.
10. **Override revoke**: platform admin `POST` an override
    `{"enabled":false}` on Org A (which had plan-granted access) -> Org A's
    `GET /drones` flipped from 200 to real HTTP 403.
11. Server stopped cleanly after verification.

## H. POSTGRES VERIFICATION

Independently queried `aerocomply_dev` directly (via a raw SQLAlchemy
connection, `psql` client not available in this environment) after the API
calls above, confirming the API-observed behavior matches the actual
stored rows exactly:

```
tenant_feature_overrides: (Org B, drone_fleet_management, enabled=True,  "M215 verification trial grant")
                           (Org A, drone_fleet_management, enabled=False, "M215 verification revoke")
subscriptions:             Org A -> m215-drone-plan (ACTIVE)
                           Org B -> m215-orgb-base   (ACTIVE)
plan_features:              m215-drone-plan  / drone_fleet_management / enabled=True
```

## I. BROWSER VERIFICATION

**NOT VERIFIED.** Per the mission's own stated priority ("API-level
verification... is the real security boundary anyway"), and given this
slice's actual security-relevant surface is entirely server-side
(`require_feature` on the API boundary, never a frontend concern), browser
verification was not performed. Section G's real HTTP verification against
the real running backend and real Postgres is the load-bearing evidence
for this slice.

**Frontend feature-key vocabulary check** (per Phase 3's instruction to
report, not silently fix, any mismatch): `frontend/lib/entitlements/
navFeatureMap.ts` (M21.4) uses speculative `FEATURE_*`-prefixed keys (e.g.
`FEATURE_WORK_ORDERS`, `FEATURE_PROCUREMENT`) drawn from
`docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md` §5's proposed catalog — **not**
the real, lowercase `ProductFeature`/`PlanFeature` keys this slice actually
protects (`work_order_management`, `drone_fleet_management`,
`procurement_management`). There is no overlap at all between the
frontend's nav-gating vocabulary and the backend's real enforced
feature_keys, and the frontend has no Drone entry in its map at all. This
is a genuine, pre-existing (M21.4-introduced) mismatch, confirmed here, not
touched or fixed by this backend-only slice.

## J. TEST RESULTS

- **Backend**: `1031 passed, 1 failed (pre-existing, unrelated), 16
  deselected` — 11 more than the `1020` baseline (this slice's new test
  file), zero new failures. The single failure is the same
  pre-existing `test_asset_foundation_phase1b.py` migration-0031 issue
  M21.4 also reported, confirmed unrelated (touches no file this slice
  changed).
- **Test-fixture maintenance** (explicitly anticipated and pre-approved by
  the mission brief): 5 pre-existing tests broke on first full-suite run
  because their fixture organizations had no subscription and now hit the
  newly-enforced `require_feature` gate on GET endpoints they exercise —
  `test_drone_operations.py` (4 tests: `test_create_get_list_drone`,
  `test_existing_aircraft_asset_not_listed_as_drone`,
  `test_viewer_can_read_not_write`, `test_cross_tenant_get_drone_returns_404`)
  and `test_tenancy_isolation.py::test_cross_tenant_cannot_get_work_order`.
  Each was fixed by adding a real `Plan`/`PlanFeature`/`Subscription` to the
  test's own organization before the GET call, via a new `_entitle_*`
  helper in each file — genuine test-fixture maintenance, not scope creep,
  each documented inline in the test file with why it was needed. No
  assertion's actual meaning was changed (isolation/RBAC assertions remain
  exactly what they were).
- **Frontend**: not run — this slice made zero frontend file changes.
  Per M21.4's last-confirmed baseline (174 passed), presumed unaffected;
  not re-verified in this backend-only slice (stated honestly, not
  claimed).
- **TypeScript**: N/A (no frontend files touched).
- **ESLint**: N/A (no frontend files touched).
- **Build**: N/A (no frontend files touched).

## K. GIT

- Files changed: `backend/app/api/v1/drones.py`,
  `backend/app/api/v1/procurement.py`, `backend/app/api/v1/work_orders.py`
  (added `Depends(require_feature(...))` to 6 GET handlers),
  `backend/scripts/seed_product_catalog.py` (added 2 real catalog entries),
  `backend/tests/integration/test_feature_entitlement_enforcement.py` (new,
  11 tests), `backend/tests/integration/test_drone_operations.py`,
  `backend/tests/integration/test_tenancy_isolation.py` (fixture
  maintenance, Section J), plus this report.
- No migration added — `require_feature`, `Plan`/`PlanFeature`/
  `Subscription`/`TenantFeatureOverride` models, and the platform admin API
  all already existed (M1/M2/M3/M17.3); this slice only added catalog rows
  (via the idempotent seed script, not a migration) and route-level
  dependencies.
- `app/core/deps.py`, `app/core/errors.py`, `app/core/permissions.py`,
  `entitlement_service.py` — **untouched**, confirmed by `git status` /
  `git diff` showing no changes to any of them.
- `backend/app/api/v1/platform.py`, `backend/app/api/v1/product_catalog.py`
  — **untouched**, confirmed no `require_feature` reference added to
  either file (`grep -n require_feature` on both returns nothing).
- Final HEAD: to be created as one new local commit, message `feat:
  enforce product entitlements at api boundary`, not amending `d3efd70` or
  any prior commit.
- Pushed: **NO**. Staging touched: **NO**. Production touched: **NO**.

## L. REMAINING GAPS (honest)

- **Only 3 features, 6 endpoints (all GET) are protected.** The other
  ~29 API routers and every POST/PATCH/approval endpoint on the 3
  protected routers remain enforced by RBAC alone, exactly as before this
  slice — by design of this slice, not an oversight. Extending
  `require_feature` further is the architecture doc's own §20 milestone 7
  ("roll out to remaining MVP-gateable routers, 3-4 at a time").
- **Frontend nav-gating vocabulary mismatch** (Section I) is real and
  unresolved — the Sidebar's UX-only gating (M21.4) does not correspond to
  any of the 3 feature_keys this slice actually enforces server-side.
  Fixing it is a frontend-only follow-up, out of this backend-only slice's
  scope.
- **`ForbiddenError`'s `code` field does not yet distinguish RBAC denial
  from entitlement denial** — both are `code="forbidden"` today; only the
  `message` text differs (`"Missing required permission: ..."` vs.
  `"Organization is not entitled to feature: ..."`). A client that
  branches on `code` alone (rather than message text) cannot currently
  tell the two apart. A dedicated `code="feature_not_entitled"` was
  considered but not added, since `ForbiddenError`'s single-`code`
  convention is used identically by every other 403 in this codebase
  (`require_permission` included) and changing it only for this one path
  would be an inconsistent, un-discussed convention change — flagged here
  as a real design question for a follow-up, not silently decided.
- **TenantFeatureOverride cannot grant access to an org with zero
  subscriptions** (Section E) — existing, correct `resolve_entitlements`
  behavior, not a bug, but a real operational constraint: a platform admin
  wanting to grant a feature to an otherwise-unsubscribed org must first
  give them some subscription (even to a near-empty base plan), not just an
  override row. Confirmed live in Section G's verification, not
  previously documented anywhere.
- No new `Permission` value, RBAC change, or `ROLE_PERMISSIONS` edit was
  made — confirmed via `git diff` on `permissions.py` (no changes).
