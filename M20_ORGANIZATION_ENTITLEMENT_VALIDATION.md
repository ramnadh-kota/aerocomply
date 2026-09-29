# M20 — Organization-Side Entitlement Validation

Chain verified: Platform Admin change → persisted → org `GET /entitlements` reflects it on the next request → frontend refetches on focus → sidebar (`NAV_FEATURE_MAP`) and route guard (`RouteEntitlementGuard`) follow → API returns 403.

Live check (preview clone, drone org, token issued before the change):
- before: `drone_fleet_management=True`, `/drones` 200, `/aircraft` 403 SUITE_ENTITLEMENT_REQUIRED
- Platform Admin `POST …/feature-overrides` disable → 201
- after (same token): `/drones` 403, `/entitlements` shows `False`

Frontend changes: refetch on focus/visibility; `hasFeature` delegates to shared `hasFeatureKey`, denies all when resolution is not ACTIVE/INACTIVE_PLAN; new `getRouteFeatureKey` + `RouteEntitlementGuard` in `(app)/layout.tsx` (blocks direct URLs, incl. detail routes).
Known limits: display fails open when `/entitlements` cannot be fetched (backend still denies); plan-default-vs-override provenance is not yet in the contract (UI shows effective state only); modules/pages are suite-level, not narrowed by features.
