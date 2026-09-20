// M21.4 built this map against speculative FEATURE_* identifiers drawn from
// docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md Section 5's *proposed* catalog
// -- none of those strings were ever real `ProductFeature.code` rows, so
// none of them ever matched anything the backend's `effective_features` map
// could actually return. M21.5 (backend-only) confirmed there is zero
// overlap and flagged it as a real mismatch without fixing it
// (M21_5_REPORT.md Section I). M21.6 fixes it here: every value in this map
// MUST equal a real, currently-seeded `ProductFeature.code` value (the same
// string PlanFeature.feature_key / TenantFeatureOverride.feature_key /
// require_feature()'s argument use -- see
// backend/app/models/product_catalog.py's ProductFeature docstring and
// backend/scripts/seed_product_catalog.py, the single source of truth).
//
// As of M21.6 there are exactly three real feature_key values, confirmed by
// reading seed_product_catalog.py directly:
//   - "work_order_management"   (backend/app/api/v1/work_orders.py)
//   - "drone_fleet_management"  (backend/app/api/v1/drones.py)
//   - "procurement_management"  (backend/app/api/v1/procurement.py)
//
// This is a UX-only lookup table, consumed by Sidebar.tsx to gray out a nav
// item when the tenant's own GET /api/v1/entitlements response
// (app/api/v1/entitlements.py, backed by app/services/entitlement_service.py)
// explicitly reports one of these three keys as disabled -- it never grants
// or denies anything itself.
//
// Deliberately partial: every M21.4 entry that named a nav route with NO
// real backing ProductFeature (aircraft, task cards, technicians, evidence,
// inspections, deferred/MEL, release readiness, maintenance program,
// vendor intelligence, compliance, regulations, assessments, warehouses --
// none of these have a ProductFeature row yet) was removed rather than
// pointed at a real key, per this slice's mission: default bias is "remove
// the speculative frontend gate," not "invent a 4th+ backend feature to
// keep the map looking complete." Those routes are simply ungated for now
// (fail-open display default below), exactly like every other href absent
// from this map. When a real ProductFeature is minted for one of them, add
// it back here pointing at the real code.
//
// /drones was added (M21.6): drone_fleet_management is real and already
// enforced server-side (app/api/v1/drones.py), but M21.4 never added a nav
// entry for it at all -- a real gap, now closed.
//
// Absence from this map means "always shown," never "always hidden" -- a
// fail-open default for *display only*, which is safe because the
// backend's own authorization (Permission checks) and its
// require_feature() enforcement (app/core/deps.py, mounted on 6 GET
// endpoints as of M21.5) remain the only real gates. This map must never be
// treated as a security boundary by any future reader of this file.
/** The only real, backend-seeded ProductFeature.code values today (see
 * backend/scripts/seed_product_catalog.py's `_CATALOG_ENTRIES`, the single
 * source of truth). This union exists so that adding a speculative key back
 * to NAV_FEATURE_MAP -- the exact M21.4 bug this slice fixed -- is a
 * TypeScript compile error, not a silent runtime no-op. Extending this union
 * is only correct once a corresponding real `ProductFeature` row (and, if it
 * should be gateable, a `require_feature(...)` mount point) has actually
 * been added on the backend first -- never speculatively. */
export type NavFeatureKey =
  | "work_order_management"
  | "drone_fleet_management"
  | "procurement_management";

export const NAV_FEATURE_MAP: Record<string, NavFeatureKey> = {
  "/maintenance/work-orders": "work_order_management",
  "/drones": "drone_fleet_management",
  "/procurement": "procurement_management",
  "/procurement/purchase-orders": "procurement_management",
};

/**
 * True only when the backend's effective_features map explicitly names this
 * feature as disabled (`=== false`). A feature key absent from the map
 * (e.g. NO_SUBSCRIPTION/SUSPENDED resolutions, which return an empty map) is
 * NOT treated as disabled here -- this function only ever narrows the
 * "always shown" default for hrefs that appear in NAV_FEATURE_MAP AND whose
 * key is explicitly present-and-false in a real resolution, so a tenant
 * with no subscription wired up yet never sees their entire nav grayed out
 * by a client-side inference the backend never made.
 */
export function isNavItemEntitlementGated(
  href: string,
  effectiveFeatures: Record<string, boolean> | null | undefined
): boolean {
  if (!effectiveFeatures) return false;
  const featureKey = NAV_FEATURE_MAP[href];
  if (!featureKey) return false;
  return effectiveFeatures[featureKey] === false;
}
