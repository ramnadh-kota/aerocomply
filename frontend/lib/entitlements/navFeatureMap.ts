// M21.4: maps a tenant NAV_GROUPS item href (Sidebar.tsx) to the
// FEATURE_* identifier that would gate it, per
// docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md Section 5's coarse,
// module-level feature catalog. This is a UX-only lookup table, consumed
// by Sidebar.tsx to gray out a nav item when the tenant's own
// GET /api/v1/entitlements response (app/api/v1/entitlements.py, backed by
// app/services/entitlement_service.py) explicitly reports that feature as
// disabled -- it never grants or denies anything itself.
//
// Deliberately coarse and deliberately partial: an href with no entry here
// has no entitlement concept yet (matches Section 5's "gateable today"
// column -- several routers, e.g. LISA/data-import/TAT/proactive, are
// explicitly flagged "needs more maturity first" and are NOT mapped, so
// they are never gated by this table until a real feature_key is minted
// for them). Absence from this map means "always shown," never "always
// hidden" -- a fail-open default for *display only*, which is safe because
// the backend's own authorization (Permission checks) and, for any route
// that later grows a require_feature() dependency, entitlement enforcement
// remain the only real gates. This map must never be treated as a security
// boundary by any future reader of this file.
export const NAV_FEATURE_MAP: Record<string, string> = {
  "/aircraft": "FEATURE_AIRCRAFT",
  "/maintenance/work-orders": "FEATURE_WORK_ORDERS",
  "/maintenance/tasks": "FEATURE_TASK_CARDS",
  "/maintenance/technicians": "FEATURE_TECHNICIANS",
  "/evidence": "FEATURE_EVIDENCE",
  "/maintenance/inspections": "FEATURE_INSPECTIONS_RII",
  "/maintenance/deferred": "FEATURE_DEFERRED_MEL",
  "/maintenance/release-readiness": "FEATURE_RELEASE_READINESS",
  "/maintenance-program": "FEATURE_MAINTENANCE_PROGRAM",
  "/maintenance/control-center": "FEATURE_MAINTENANCE_PROGRAM",
  "/procurement": "FEATURE_PROCUREMENT",
  "/procurement/purchase-orders": "FEATURE_PROCUREMENT",
  "/procurement/vendors": "FEATURE_VENDOR_INTELLIGENCE",
  "/compliance": "FEATURE_COMPLIANCE",
  "/regulations": "FEATURE_COMPLIANCE",
  "/assessments": "FEATURE_ASSESSMENTS",
  "/facilities": "FEATURE_WAREHOUSES",
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
