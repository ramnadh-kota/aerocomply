# M21.6 — Frontend Nav Entitlement Key Correction

Date: 2026-09-20
Branch: main (local only)

## 1. HEAD before work

`c3d9895` (M21.5 — backend entitlement enforcement at the API boundary,
local commit, unpushed).

## 2. Files inspected

- `frontend/lib/entitlements/navFeatureMap.ts` (M21.4, the file with the bug)
- `frontend/lib/entitlements/useMyEntitlements.ts` (M21.4)
- `frontend/components/layout/Sidebar.tsx` (consumer: `isNavItemEntitlementGated`
  call site around line 205, `NAV_GROUPS`/`PLATFORM_NAV_GROUPS`)
- `backend/app/models/product_catalog.py` (`ProductFeature` model —
  confirmed the column is `code: Mapped[str]` (unique, indexed), documented
  in its own docstring as the same string `PlanFeature.feature_key` /
  `TenantFeatureOverride.feature_key` / `require_feature()`'s argument use)
- `backend/scripts/seed_product_catalog.py` (`_CATALOG_ENTRIES`, the real
  seed data — read in full, confirmed directly, not assumed)
- `backend/app/api/v1/*` — grepped for `require_feature(` across the whole
  directory
- `frontend/tests/sidebar-navigation.test.ts` and
  `frontend/tests/entitlement-admin.test.ts` (existing test conventions —
  no RTL, pure-function/data-contract tests via vitest)
- `M21_5_REPORT.md` (Section I, the report that found and documented, but
  did not fix, this exact mismatch)

## 3. Complete frontend feature-key inventory

`grep -rn require_feature backend/app/api/v1/` returned exactly 6 matches,
across 3 routers, confirming exactly 3 real backend-enforced feature_keys
exist today: `work_order_management` (`work_orders.py`),
`drone_fleet_management` (`drones.py`), `procurement_management`
(`procurement.py`). `seed_product_catalog.py`'s `_CATALOG_ENTRIES` list
independently confirms the same 3 `ProductFeature.code` rows — no others.

| Old NAV_FEATURE_MAP key (M21.4) | Href | Classification |
|---|---|---|
| `FEATURE_AIRCRAFT` | `/aircraft` | C — speculative, no backend feature |
| `FEATURE_WORK_ORDERS` | `/maintenance/work-orders` | B — mismatch (real capability, wrong string) |
| `FEATURE_TASK_CARDS` | `/maintenance/tasks` | C — speculative |
| `FEATURE_TECHNICIANS` | `/maintenance/technicians` | C — speculative |
| `FEATURE_EVIDENCE` | `/evidence` | C — speculative |
| `FEATURE_INSPECTIONS_RII` | `/maintenance/inspections` | C — speculative |
| `FEATURE_DEFERRED_MEL` | `/maintenance/deferred` | C — speculative |
| `FEATURE_RELEASE_READINESS` | `/maintenance/release-readiness` | C — speculative |
| `FEATURE_MAINTENANCE_PROGRAM` | `/maintenance-program` | C — speculative |
| `FEATURE_MAINTENANCE_PROGRAM` | `/maintenance/control-center` | C — speculative |
| `FEATURE_PROCUREMENT` | `/procurement` | B — mismatch |
| `FEATURE_PROCUREMENT` | `/procurement/purchase-orders` | B — mismatch |
| `FEATURE_VENDOR_INTELLIGENCE` | `/procurement/vendors` | C — speculative |
| `FEATURE_COMPLIANCE` | `/compliance` | C — speculative |
| `FEATURE_COMPLIANCE` | `/regulations` | C — speculative |
| `FEATURE_ASSESSMENTS` | `/assessments` | C — speculative |
| `FEATURE_WAREHOUSES` | `/facilities` | C — speculative |
| (none — missing entirely) | `/drones` | D — real backend feature (`drone_fleet_management`), zero frontend mapping |

Every one of the 17 M21.4 entries turned out to be class B or C — there was
**no** class-A exact match anywhere in the original map (confirms M21.5's
"zero overlap" finding directly, from the frontend side).

## 4. Exact mapping table (nav item -> old key -> authoritative backend key -> status)

| Nav item | Old key | Authoritative backend key | Status |
|---|---|---|---|
| `/maintenance/work-orders` | `FEATURE_WORK_ORDERS` | `work_order_management` | Fixed (B -> corrected) |
| `/procurement` | `FEATURE_PROCUREMENT` | `procurement_management` | Fixed (B -> corrected) |
| `/procurement/purchase-orders` | `FEATURE_PROCUREMENT` | `procurement_management` | Fixed (B -> corrected) |
| `/drones` | (none) | `drone_fleet_management` | Added (D -> filled) |
| All 13 other M21.4 hrefs (aircraft, tasks, technicians, evidence, inspections, deferred, release-readiness, maintenance-program x2, vendors, compliance, regulations, assessments, facilities) | `FEATURE_*` | none | Removed — nav item now simply ungated (absent from map = "always shown", the pre-existing fail-open default) |

## 5. Mappings removed as speculative

13 entries removed (listed in the table above). Each corresponds to a real,
shipped frontend page, but none has a `ProductFeature` row or a
`require_feature()`-protected endpoint backing it today. Per the mission's
explicit bias ("default bias is remove the speculative frontend gate, not
add more backend catalog entries"), no 4th+ `ProductFeature` was invented
to preserve map completeness — these routes are simply ungated for display
purposes now, identical in effect to every other href that was already
absent from the map (e.g. `/dashboard`, `/findings`, `/reports` were never
in the M21.4 map either).

## 6. Backend ProductFeature records added

**None.** Per the mission's stated expectation ("expect: none, or
justify"), no new `ProductFeature`, `ProductModule`, `ProductSuite`, or
`ProductPage` row was added. `git diff` confirms zero backend files were
touched by this slice — the only 2 files changed are
`frontend/lib/entitlements/navFeatureMap.ts` and the new
`frontend/tests/nav-feature-map.test.ts`.

## 7. Tests added/changed

New file `frontend/tests/nav-feature-map.test.ts` (10 new tests), following
this repo's existing pure-function/data-contract convention (no RTL, same
pattern as `sidebar-navigation.test.ts` and `entitlement-admin.test.ts`):

- Every `NAV_FEATURE_MAP` value is one of the 3 real backend feature_keys
  (a literal list duplicated in the test, since the frontend test runner
  has no access to the Python seed script).
- Every mapped href still exists in the real `NAV_GROUPS`.
- No value starts with the old `FEATURE_` prefix.
- `/drones` maps to `drone_fleet_management` (the closed gap).
- Work-order and procurement routes map to their corrected backend keys.
- `isNavItemEntitlementGated`: gates when the real key is explicitly
  `false`; does not gate when `true`; does not gate a route with no
  `ProductFeature` (e.g. `/aircraft`) even with other keys present; fails
  open on `null`/`undefined` (`NO_SUBSCRIPTION`/fetch-failure case); does
  not gate when the key is simply absent from the resolution map.

`navFeatureMap.ts` itself also picked up (observed after editing, not
manually added by hand — reviewed and kept, since it directly implements
the mission's own instruction to "add clear TypeScript typing... making
explicit that these strings must equal backend ProductFeature.feature_key
values") an exported `NavFeatureKey` string-literal union type
(`"work_order_management" | "drone_fleet_management" |
"procurement_management"`) that `NAV_FEATURE_MAP`'s value type is now
constrained to, so reintroducing a speculative key is a compile error, not
a silent runtime no-op.

## 8. Backend test result

Not run. No backend file was changed by this slice (Section 6), so per the
mission's own instruction ("only touch if you add a ProductFeature seed
entry... rare/unlikely") the backend suite was not re-run. Last known
backend baseline (M21.5, `c3d9895`): `1031 passed, 1 failed (pre-existing,
unrelated), 16 deselected`.

## 9. Frontend test result

`npx vitest run` (full suite): **184 passed** (174 baseline as of `c3d9895`
+ 10 new tests in `nav-feature-map.test.ts`), 14 test files, 0 failures.

## 10. TypeScript result

`npx tsc --noEmit`: clean, no output, exit 0.

## 11. ESLint result

`npx eslint lib/entitlements/navFeatureMap.ts tests/nav-feature-map.test.ts`:
clean, no output, exit 0.

## 12. Build result

`npm run build`: succeeded. Full route manifest generated, including
`/drones`, `/procurement`, `/procurement/purchase-orders`,
`/maintenance/work-orders` — no build errors. (`frontend/next-env.d.ts` was
touched by the build as an auto-generated, unrelated side effect — left
unstaged/uncommitted, not part of this change.)

## 13. Browser verification result

**Partially verified, rest NOT VERIFIED.** Started the real local stack:
backend `uvicorn app.main:app --port 8001` against `aerocomply_dev`, and
the frontend dev server via `preview_start` (`aerocomply-dev`, port 3000).

Verified live:
- Registered a real new organization (`M216 Verify Org`,
  `m216.verify@example.com`) via the real
  `POST /auth/register-organization` API (no subscription attached).
- Logged in through the real login UI in the browser.
- Confirmed via `find`/`read_page` that the sidebar renders a real
  `"Drones"` link at `/drones` (the previously-missing D-class mapping now
  present) with no `aria-disabled`/lock styling — correct, since an org
  with **zero subscriptions** resolves to a `null` `effectiveFeatures` map,
  which `isNavItemEntitlementGated` fails open on by design (unit-tested in
  Section 7), so nothing should be shown as locked for this org regardless
  of the corrected keys.
- No new console errors traceable to this change; the several 401/403/404
  console errors observed are pre-existing dashboard-widget calls for a
  brand-new org with no subscription/data, unrelated to
  `navFeatureMap.ts` (that file only affects `Sidebar.tsx`'s gating
  display, not any widget's own API calls).

**NOT VERIFIED**: the actual visually-locked/grayed-out state for a nav
item whose real feature_key is explicitly disabled on an active plan (the
`entitlementDenied === true` branch in `Sidebar.tsx`). Setting that up
requires the platform admin flow (create plan, subscribe org, optionally
add a `TenantFeatureOverride`) that M21.5 exercised; a pre-existing
platform admin account was found in `aerocomply_dev`
(`m215.platadmin@example.com`) but its password from that prior session is
unknown, and `create_platform_admin.py` is not idempotent for password
resets, so a fresh one could have been minted but this was not completed
within this slice's time budget. The `false`-branch behavior of
`isNavItemEntitlementGated` is unit-tested directly (Section 7) with the
exact `effectiveFeatures` shape the real backend `/entitlements` endpoint
returns, and M21.5 already proved the underlying backend
entitled/unentitled 200/403 behavior live end-to-end for
`drone_fleet_management` — so the mechanism is proven on both sides
independently, but the full live visual integration of "disabled feature
-> grayed nav item in the browser" specifically was not clicked through.

Both servers stopped cleanly after that verification pass (uvicorn PID
killed, `preview_stop` called on the frontend dev server).

**Continuation-session addendum**: this task was resumed in a second
session on the same working tree (same `f18964b` commit already present,
untouched). In the continuation, the Browser tool's `navigate` call to
`http://localhost:3000` was denied/failed on every retry (a tool/session
environment limitation, not an application error) after the local backend
and Postgres were restarted, so no further live-UI clicking was possible in
this pass. Instead, the locked-vs-unlocked mechanism that Section 13's first
pass left unverified was checked one level down, at the exact API contract
`Sidebar.tsx`/`navFeatureMap.ts` consume, against two freshly-registered
real organizations, a freshly-created real `PLATFORM_ADMIN`
(`m216.platadmin@example.com`), and real HTTP against a `uvicorn` instance
restarted on port 8001 (the port the frontend's own build actually calls,
confirmed via `read_network_requests` after the first login attempt failed
with `ERR_CONNECTION_REFUSED` against 8001 while only 8010 was listening --
a real, fixed discrepancy, not assumed):

- Created plan `m216-drone-plan` with `PlanFeature(drone_fleet_management,
  enabled=true)`, subscribed a fresh Org A to it (`ACTIVE`).
- Left a fresh Org B with zero subscriptions.
- `GET /api/v1/entitlements` (real HTTP, real JWT) for Org A returned
  `effective_features: {"drone_fleet_management": true}`; for Org B,
  `resolution_status: "NO_SUBSCRIPTION"`, `effective_features: {}`.
- `GET /api/v1/drones`: Org A -> real HTTP 200; Org B -> real HTTP 403.
- Fed Org A's exact `effective_features` shape into
  `isNavItemEntitlementGated("/drones", {"drone_fleet_management": true})`
  (already covered by the Section 7 unit tests) -> `false` (not gated) --
  correctly matching the real 200. Org B's empty-map shape correctly
  produces `false` too (fail-open display default), which is the documented,
  intentional behavior (a tenant with no subscription never sees their nav
  grayed out from a client-side inference the backend never made) --
  confirmed against the real API response shape, not merely asserted in the
  abstract.
- This confirms end-to-end, with real data, that the corrected
  `NAV_FEATURE_MAP` keys line up exactly with what the real backend
  actually returns for both an entitled and an unentitled organization.

**Still NOT VERIFIED in either session**: the browser-rendered
`entitlementDenied === true` visual state (grayed nav item + lock glyph +
tooltip) for a nav item whose real feature_key is explicitly disabled
(`false`, not merely absent) on an active plan -- this needs a plan that
includes the feature as `enabled: false` (or a revoking
`TenantFeatureOverride`) plus an actual click-through in a rendered page,
which the Browser tool's denied navigation prevented in this continuation
session. The `Sidebar.tsx` code path and the `isNavItemEntitlementGated`
function it calls are unit-tested for exactly this case (Section 7,
`effectiveFeatures: { work_order_management: false }` -> `true`), so the
logic is proven; only the pixels were not observed.

## 14. Database verification result

Queried `aerocomply_dev` directly via a raw SQLAlchemy connection (`psql`
not available in this environment, same limitation M21.5 noted):

```
select code from product_features order by code;
[('drone_fleet_management',), ('procurement_management',), ('work_order_management',)]
```

Confirms exactly 3 real feature_key rows, exactly matching
`NAV_FEATURE_MAP`'s 3 corrected values — no drift between the live
database and the frontend map. Re-confirmed identically in the
continuation session (same query, same 3 rows, no duplicates, run again
after registering the two fresh Section 13-addendum organizations, proving
the catalog itself was not mutated by that verification traffic).

## 15. Tenant-isolation result

Not applicable to this slice — it changes zero backend authorization code
and zero backend query logic. Tenant isolation for the actual API boundary
was already proven by M21.5 (`test_feature_entitlement_enforcement.py`,
"Tenant isolation: Org B's entitlement never satisfies Org A's check").
This slice only changes which client-side UX string a nav item is
compared against; the real security boundary (`require_feature` on the
backend) is untouched, confirmed by `git diff` showing zero backend file
changes.

## 16. Remaining gaps

- Live visual verification of the "explicitly disabled feature -> grayed
  nav item" browser state was not completed (Section 13) — recommend a
  short follow-up that creates a fresh platform admin, a plan excluding
  `work_order_management`, subscribes a test org, and confirms the
  `/maintenance/work-orders` link renders with the locked tooltip.
- 13 real, shipped frontend pages (aircraft, tasks, technicians, evidence,
  inspections, deferred/MEL, release readiness, maintenance program x2,
  vendors, compliance, regulations, assessments, facilities/warehouses)
  have no entitlement concept on either side of the stack yet. This is
  unchanged by this slice (by design) and matches the existing
  architecture doc's own "needs more maturity first" framing for
  not-yet-gateable routes — a real backlog item, not something this slice
  was scoped to close.
- `ForbiddenError`'s single `code="forbidden"` (RBAC vs. entitlement
  indistinguishable by code alone) remains exactly as M21.5 left it and
  flagged it — out of scope for a frontend-only slice.

## 17. Final commit hash

`f18964b` — `fix: correct frontend nav entitlement keys to real backend
feature_keys`, 2 files changed (`frontend/lib/entitlements/navFeatureMap.ts`,
new `frontend/tests/nav-feature-map.test.ts`), not amending `c3d9895` or any
prior commit. Not pushed. Neon production (`bitter-tooth-52841705`) and
Neon/Render staging (`small-meadow-85982633` / `aerocomply-backend-staging`)
were never touched, connected to, or referenced — only the local native
Postgres service on `localhost:55432/aerocomply_dev` was used.
