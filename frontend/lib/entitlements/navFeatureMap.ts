import { FEATURE_KEYS, canonicalizeFeatureKey, type FeatureKey } from "./featureKeys";

export type NavFeatureKey = FeatureKey | string;

export const NAV_FEATURE_MAP: Record<string, NavFeatureKey> = {
  // Maintenance & Work Orders
  "/maintenance/work-orders": FEATURE_KEYS.WORK_ORDER_MANAGEMENT,
  "/maintenance/tasks": FEATURE_KEYS.WORK_ORDER_MANAGEMENT,
  "/maintenance/planning": FEATURE_KEYS.WORK_ORDER_MANAGEMENT,
  "/maintenance/projects": FEATURE_KEYS.WORK_ORDER_MANAGEMENT,
  "/maintenance/operations": FEATURE_KEYS.WORK_ORDER_MANAGEMENT,

  // Inspections & Release
  "/maintenance/inspections": FEATURE_KEYS.INSPECTIONS_MANAGEMENT,
  "/maintenance/release-readiness": FEATURE_KEYS.RELEASE_READINESS,

  // Fleet Operations & Assets
  "/aircraft": FEATURE_KEYS.AIRCRAFT_FLEET_MANAGEMENT,
  "/drones": FEATURE_KEYS.DRONE_FLEET_MANAGEMENT,
  "/helicopters": FEATURE_KEYS.HELICOPTER_FLEET_MANAGEMENT,
  "/evtols": FEATURE_KEYS.EVTOL_FLEET_MANAGEMENT,

  // Drone Operations workspace — all /drone-ops/* routes are entitlement-gated
  // via the SuiteGuard in the layout. The sidebar links directly to /drone-ops/overview.
  "/drone-ops/overview": FEATURE_KEYS.DRONE_FLEET_MANAGEMENT,

  // Data acquisition (ingest endpoint is gated by flight_telemetry on the backend)
  "/data-sources": FEATURE_KEYS.FLIGHT_TELEMETRY,

  // Procurement
  "/procurement": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  "/procurement/parts": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  "/procurement/cart": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  "/procurement/approvals": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  "/procurement/purchase-orders": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  "/procurement/vendors": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,

  // Compliance & Regulations
  "/compliance": FEATURE_KEYS.COMPLIANCE_MANAGEMENT,
  "/regulations": FEATURE_KEYS.COMPLIANCE_MANAGEMENT,
  "/compliance/regulatory-register": FEATURE_KEYS.COMPLIANCE_MANAGEMENT,
  // The assessments API is gated by advanced_compliance_intelligence on the backend; the route mirrors it.
  "/assessments": FEATURE_KEYS.ADVANCED_COMPLIANCE_INTELLIGENCE,
  // Parts inventory reads /parts, which the backend gates with procurement_management.
  "/maintenance/parts": FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  "/assessment-intelligence": FEATURE_KEYS.ADVANCED_COMPLIANCE_INTELLIGENCE,

  // AI & LISA
  "/ai": FEATURE_KEYS.LISA_AI_COPILOT,

  // Intelligence & Analytics
  "/fleet/health": FEATURE_KEYS.PREDICTIVE_MAINTENANCE,
  "/intelligence/fleet": FEATURE_KEYS.MRO_INTELLIGENCE,

  // Audit
  "/audit": FEATURE_KEYS.AUDIT_LOGGING,
  "/tenant/audit": FEATURE_KEYS.AUDIT_LOGGING,
};

/**
 * True only when the backend's effective_features map explicitly names this
 * feature as disabled (`=== false`). A feature key absent from the map
 * (e.g. NO_SUBSCRIPTION/SUSPENDED resolutions, which return an empty map) is
 * NOT treated as disabled here -- this function only ever narrows the
 * "always shown" default for hrefs that appear in NAV_FEATURE_MAP AND whose
 * key is explicitly present-and-false in a real resolution.
 */
export function isNavItemEntitlementGated(
  href: string,
  effectiveFeatures: Record<string, boolean> | null | undefined
): boolean {
  if (!effectiveFeatures) return false;
  const featureKey = NAV_FEATURE_MAP[href];
  if (!featureKey) return false;
  const canonical = canonicalizeFeatureKey(featureKey);

  if (effectiveFeatures[featureKey] !== undefined) {
    return effectiveFeatures[featureKey] === false;
  }
  if (effectiveFeatures[canonical] !== undefined) {
    return effectiveFeatures[canonical] === false;
  }
  if (effectiveFeatures[featureKey.toUpperCase()] !== undefined) {
    return effectiveFeatures[featureKey.toUpperCase()] === false;
  }
  if (effectiveFeatures[canonical.toUpperCase()] !== undefined) {
    return effectiveFeatures[canonical.toUpperCase()] === false;
  }
  return false;
}

/**
 * Strict counterpart used by the sidebar: mirrors the route guard and the backend (absent from the plan = not
 * entitled, except baseline features). `hasFeature` is EntitlementContext.hasFeature, which already fails open while
 * the resolution is still loading and denies every feature for a non-granting subscription status.
 */
export function isNavItemUnavailable(href: string, hasFeature: (featureKey: string) => boolean): boolean {
  const featureKey = NAV_FEATURE_MAP[href];
  if (!featureKey) return false;
  return !hasFeature(featureKey);
}

/**
 * Feature key gating a route, or null when the route is not commercially
 * gated. Longest-prefix match on NAV_FEATURE_MAP so detail routes
 * (e.g. /aircraft/123) inherit their section's feature. One map drives both
 * sidebar and route protection -- no second route table.
 */
export function getRouteFeatureKey(pathname: string): NavFeatureKey | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  let best: string | null = null;
  for (const href of Object.keys(NAV_FEATURE_MAP)) {
    if (path === href || path.startsWith(href + "/")) {
      if (best === null || href.length > best.length) best = href;
    }
  }
  return best === null ? null : NAV_FEATURE_MAP[best];
}

/** Platform-administration routes: only platform operators may use them. */
export function isPlatformPath(pathname: string): boolean {
  return pathname === "/platform" || pathname.startsWith("/platform/");
}

export function isPlatformRole(roles: readonly string[] | undefined | null): boolean {
  return (roles ?? []).some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF");
}
