# M4.2 — Fleet Intelligence Control Center

## 1. Failure isolation result

A new cluster (9 tests, `test_work_order_lifecycle_api.py`) appeared in the
full backend suite after the M4.2 backend addition, raising the failure
count from the previously-documented 92 to 126. This was **not** assumed
pre-existing on the basis of matching error messages. A surgical isolation
comparison was performed:

- **Baseline A** (M4.2 present): full suite → 126 failed, 1355 passed.
- **Baseline B** (M4.2 completely removed — `fleet_intelligence_service.py`
  deleted, `FleetAssetIntelligence`/`FleetIntelligenceSummary` schema
  classes removed, the `/fleet` endpoint and its router import removed, the
  M4.2 test file removed; D1/D2.1/D2.2 Pass 1-3/platform hardening/all other
  router registrations left untouched): full suite → 126 failed, 1349
  passed (exactly 6 fewer — the removed M4.2 tests).
- **Exact-set comparison** (`comm` on sorted, deduplicated failure-name
  lists, both directions): **zero difference**. The identical 126 test
  names fail in both baselines.

**Classification: A — confirmed pre-existing/unrelated.** The
`test_work_order_lifecycle_api.py` cluster shares the same root cause
already documented in `D2_2_BACKEND_FAILURE_BASELINE.md`
(`register_organization` never provisions a `Subscription`/`Plan`, so
`require_feature(...)` 403s) — it was gating `drone_fleet_management`
there; here it gates `work_order_management`. The cluster's absence from
the earlier 92-count audit means it was not exercised by whatever test
subset/order that audit's runs happened to hit, not that M4.2 introduced
it — the isolation comparison proves this directly, independent of shared
error text.

M4.2 was fully restored after the comparison; all 44 D2.2 backend tests
(6 new fleet + 38 from Pass 1-3) pass in the restored state.

## 2. Backend implementation

Smallest possible addition, reusing existing services with zero new
intelligence rules:

- `app/schemas/intelligence.py`: `FleetAssetIntelligence`,
  `FleetIntelligenceSummary` (additive).
- `app/services/intelligence/fleet_intelligence_service.py` (new):
  `get_fleet_intelligence_summary(db, *, organization_id)` — calls
  `asset_service.list_assets` (Developer 1's own, already tenant-scoped,
  already the canonical cross-asset-type lister) then, per asset,
  `get_asset_readiness_intelligence` (for `operational_state` and
  `aerospace_intelligence_status`, the two fields not echoed onto
  `AssetDecision`/`AssetRecommendation`) and `get_asset_recommendation`
  (which itself cascades through decision → priority → risk → readiness,
  yielding everything else in one call). Two calls per asset, not five.
- `app/api/v1/intelligence.py`: `GET /intelligence/fleet` →
  `FleetIntelligenceSummary`, same `require_permission(Permission.AIRCRAFT_READ)`
  pattern as every other D2.2 endpoint.
- `tests/integration/test_fleet_intelligence_service.py` (new, 6 tests):
  empty org, real multi-asset summary, `UNKNOWN`/`INSUFFICIENT_DATA`
  preservation, AOG/CRITICAL surfacing, blocker traceability, tenant
  isolation.

## 3. Fleet API contract

```
GET /api/v1/intelligence/fleet -> FleetIntelligenceSummary
{
  total_assets: number,
  assets: FleetAssetIntelligence[],
  evaluated_at: string
}
```
`FleetAssetIntelligence` mirrors the per-asset endpoints' fields
(`readiness_state`, `risk_level`, `priority_level`, `decision_state`,
`decision_reason`, `blockers`, `warnings`) plus `asset_id`, `registration`,
`asset_type`, `operational_state`, `aerospace_intelligence_status`,
`top_recommendation_action` (first recommendation item's action text, or
`null`), `blocker_count`, `warning_count`.

## 4. Frontend implementation

- `lib/api/intelligence.ts`: added `getFleet` + `FleetAssetIntelligence`/
  `FleetIntelligenceSummary` types (same file, same conventions as the 5
  per-asset functions — no second API client).
- `app/(app)/intelligence/fleet/page.tsx` (new): the Control Center page.
- `components/layout/Sidebar.tsx`: added one nav entry ("Fleet
  Intelligence" under Operations) — updated `tests/sidebar-navigation.test.ts`'s
  hardcoded nav-count assertion from 65 to 66 (a real, deliberate count
  change, not a weakened test).
- `app/(app)/assets/[id]/page.tsx`: added `?tab=INTELLIGENCE` URL support
  (reads `useSearchParams().get("tab")` to set the initial `activeTab`) so
  fleet-page drill-down links can open directly onto the Intelligence tab
  built in M4.1/M4.3 — reusing the existing tab-state architecture, not a
  second asset-detail implementation.
- `tests/fleet-intelligence.test.ts` (new, 14 tests).

## 5. Control Center structure (implemented, matches your suggested layout)

Fleet State (operational/intelligence/readiness/risk/priority/decision
distributions, each a tally of already-computed backend values) → Attention
Required (clickable KPI cards: Critical/High/Action Required/Monitor/
Insufficient Data) → Fleet Asset Intelligence table (filterable, one row per
asset, click-to-expand traceability) → Blockers (flattened fleet-wide,
required/resolution action columns) → Warnings (flattened fleet-wide) →
Uncertainty (assets with any `UNKNOWN`/`UNKNOWN_INTEL`/`INSUFFICIENT_DATA`
signal) → Traceability (selected asset's decision → recommendation →
blocker chain, plus a link into the asset's own full Intelligence tab).

## 6. Data flow

One `GET /intelligence/fleet` call per page load (not N×5 — the exact
performance constraint from your brief). All KPI tallies, distributions,
and the uncertainty list are computed client-side via `useMemo`, but only
by **counting/filtering already-computed backend enum values** — no
readiness/risk/priority/decision/recommendation logic is derived in
TypeScript.

## 7. Filters

Client-side only, over the single fetched dataset: asset type, operational
state, decision state (dropdowns populated from `distinctValues()` — only
values actually present in the response, never a hardcoded option list),
plus the five clickable "Attention Required" KPI cards as a sixth filter
dimension. None of these change what a value means — they only narrow
which already-computed rows are displayed.

## 8. Drill-down

Every asset reference (`asset_type`/blocker/warning table rows, uncertainty
cards, traceability panel) links to `/assets/{assetId}?tab=INTELLIGENCE`,
which now opens directly onto the existing M4.3 Intelligence tab instead of
defaulting to Overview.

## 9. UNKNOWN handling

`intelligenceAerospaceStatusBadge`, `intelligenceReadinessBadge`,
`intelligenceRiskLevelBadge`, and `intelligenceDecisionBadge` (all from
M4.4, reused unchanged) map `UNKNOWN_INTEL`/`UNKNOWN`/`INSUFFICIENT_DATA` to
the `INSUFFICIENT_DATA` badge kind (amber/distinct), never to
`COMPLIANT`/green. Verified by test:
`isUncertain()` is exercised for all four UNKNOWN-shaped conditions, and a
dedicated test confirms `INSUFFICIENT_DATA` and `NO_ACTION_REQUIRED` are
never conflated.

## 10. Traceability

Selecting a fleet-table row expands an inline panel showing that asset's
`decision_reason`, `top_recommendation_action`, and full blocker list (each
with `source_domain`, `description`, `related_record_type`/`related_record_id`)
— plus a link to the asset's own Intelligence tab for the complete
per-blocker `required_action`/`resolution_action`/`regulatory_reference`
detail already built in M4.3.

## 11. Tenant/security behavior

No new auth path. `useSession()`/`accessToken` exactly as every other page;
`organization_id` is never sent from the client (verified by test asserting
the request body never contains that string); the backend endpoint enforces
isolation identically to the other 5 D2.2 endpoints (same
`require_permission` dependency, same JWT-derived `organization_id`).

## 12. Tests

Backend: 6 new (44/44 D2.2 total pass). Frontend: 14 new
(`tests/fleet-intelligence.test.ts`) covering API call correctness, real
vs. empty vs. error responses, blocker/warning field preservation, and all
four UNKNOWN-shaped `isUncertain()`/`distinctValues()` cases. Full frontend
suite: **28/28 files, 325/325 tests pass** (one pre-existing test's
hardcoded nav-count updated from 65→66 to reflect the new, real nav item —
not weakened, just corrected).

## 13. Typecheck

`tsc --noEmit`: 0 errors.

## 14. Lint

`eslint .`: 0 errors (117 pre-existing warnings, zero in any file this
milestone touched or created).

## 15. Production build

`next build`: exit 0, "Compiled successfully", `/intelligence/fleet` present
in the route manifest as a static page.

## 16. Remaining known failures

126 pre-existing, unrelated backend failures (confirmed Category A by
isolation comparison in §1) — the same entitlement-provisioning defect
class documented in `D2_2_BACKEND_FAILURE_BASELINE.md`, now also observed
gating `work_order_management` in addition to `drone_fleet_management`.
Not touched, not modified, not skipped/xfail'd, per instruction.

## 17. M4.2 status: **COMPLETE**

Both halves delivered and validated:
- Backend: `GET /intelligence/fleet`, 6 tests passing, ruff/mypy clean.
- Frontend: Fleet Intelligence Control Center page, 14 tests passing,
  typecheck/lint/build clean, drill-down wired into the existing asset
  Intelligence tab.

## 18. Next milestone

M4.5 (Intelligence Context contract for future Kota AI) — still deferred
per your earlier scoping decision. Recommended next: either pick that up,
or address the now twice-observed organization-provisioning entitlement
defect (outside D2.2/M4 ownership, but blocking an increasing share of the
regression suite) before it grows further.
