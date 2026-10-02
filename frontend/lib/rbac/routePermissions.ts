/**
 * Route -> RBAC permission map (display side).
 *
 * The backend is the only enforcement point (`require_permission` on every API route); this map mirrors what each
 * page's API calls require so the sidebar and direct URLs agree with it instead of showing pages that can only fail
 * with 403s. Each value is an ANY-OF list: the route is available if the user holds at least one listed permission.
 * Permission strings are the backend `Permission` values and are delivered in `/auth/me` (`permissions`), computed
 * from the same `ROLE_PERMISSIONS` table the API checks. tests/route-permissions.test.ts verifies every string here
 * is a real backend permission.
 *
 * Longest-prefix match, so `/maintenance/parts` overrides `/maintenance`. Routes that are not listed (dashboard,
 * notifications, LISA, tenant profile/subscription/usage, ...) need no specific permission.
 */
export const ROUTE_PERMISSIONS: Record<string, readonly string[]> = {
  // Fleet / assets
  "/aircraft": ["aircraft:read"],
  "/fleet": ["aircraft:read"],
  "/engines": ["aircraft:read"],
  "/components": ["aircraft:read"],
  "/drones": ["drone:read"],
  "/helicopters": ["aircraft:read", "drone:read"],
  "/evtols": ["aircraft:read", "drone:read"],
  "/assets": ["aircraft:read", "drone:read"],
  "/data-sources": ["drone:read"],
  "/facilities": ["facility:read"],
  "/intelligence": ["aircraft:read"],
  // Maintenance
  "/maintenance": ["aircraft:read"],
  "/maintenance-program": ["aircraft:read"],
  "/maintenance/parts": ["part:read"],
  "/maintenance/inspections": ["inspection:read"],
  "/maintenance/technicians": ["technician:read"],
  // Compliance & evidence
  "/compliance": ["compliance:assess", "regulation:read"],
  "/regulations": ["regulation:read"],
  "/assessments": ["assessment:read"],
  "/assessment-intelligence": ["assessment:read"],
  "/evidence": ["evidence:read"],
  "/findings": ["inspection:read"],
  "/audit": ["audit:read"],
  // Procurement
  "/procurement": ["procurement:read"],
  "/procurement/parts": ["part:read"],
  // Administration
  "/data-import": ["org:manage"],
  "/tenant/users": ["user:manage"],
  "/tenant/roles": ["user:manage"],
  "/tenant/invitations": ["user:manage"],
  "/tenant/teams": ["user:manage"],
  "/tenant/audit": ["audit:read"],
  // Usage limits are commercial terms (backend: GET /tenant/usage requires org:manage).
  "/tenant/usage": ["org:manage"],
};

function normalize(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
}

/** Permissions (any-of) the route requires, or null when it needs none. */
export function getRoutePermissions(pathname: string): readonly string[] | null {
  const path = normalize(pathname);
  let best: string | null = null;
  for (const prefix of Object.keys(ROUTE_PERMISSIONS)) {
    if (path === prefix || path.startsWith(prefix + "/")) {
      if (best === null || prefix.length > best.length) best = prefix;
    }
  }
  return best === null ? null : ROUTE_PERMISSIONS[best];
}

/**
 * True when the user is known to LACK the permission(s) the route needs. `permissions` undefined/null means "not
 * known" (still loading, or an older API) and is never treated as a denial -- the backend still enforces.
 */
export function isRouteForbidden(pathname: string, permissions: readonly string[] | null | undefined): boolean {
  if (!permissions) return false;
  const required = getRoutePermissions(pathname);
  if (!required) return false;
  return !required.some((p) => permissions.includes(p));
}
