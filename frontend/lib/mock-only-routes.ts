// Pages that render ONLY bundled sample data (no live-API code path and no demo gate).
//
// A real (non-demo) session must never see fabricated records presented as its own, so RouteEntitlementGuard replaces
// these routes with a "not connected to live data" notice. Demo sessions keep the sample-data pages. The list is
// verified against the filesystem by tests/mock-only-routes.test.ts: adding a page that imports lib/mock|lib/demo
// without a live-API path, a demo gate or a withLive(...) wrapper fails that test until the page is either connected to the API (preferred) or
// registered here. Remove a route from this list when its page is wired to the backend.

export const MOCK_ONLY_ROUTES: readonly string[] = [
  "/aircraft/[id]/configuration",
  "/assessments/[id]/review",
  "/audit",
  "/automation",
  "/compliance/pre-audit",
  "/documents",
  "/evidence/[id]",
  "/executive",
  "/finance",
  "/finance/[id]",
  "/fleet/aircraft/[id]/health",
  "/fleet/health",
  "/integrations",
  "/maintenance/discrepancies",
  "/maintenance/material-readiness",
  "/maintenance/planning",
  "/maintenance/planning/[id]",
  "/maintenance/projects",
  "/maintenance/projects/[id]",
  "/maintenance/projects/[id]/intelligence",
  "/maintenance/records",
  "/maintenance/release-readiness",
  "/maintenance/tasks",
  "/organization/readiness",
  "/organization/roles/[id]",
  "/organization/roles/new",
  "/organization/usage",
  "/organization/users/[id]",
  "/pilot",
  "/platform/features",
  "/procurement/cart",
  "/reports",
  "/reports/[id]",
  "/workspace",
];

/**
 * Pages that MIX a live section with sample-data sections and have no live-only variant yet. A live session must not see
 * the sample sections presented as its own records, so these are treated exactly like the mock-only pages above
 * (notice / redirect). Each must exist as a page file (verified by tests/mock-only-routes.test.ts); remove an entry when
 * the page gets a live variant (withLive) that renders only real data.
 */
export const SAMPLE_SECTION_ROUTES: readonly string[] = [
  "/maintenance/control-tower",
  "/maintenance/hangar",
  "/maintenance/operations",
];

/**
 * Mock-only pages whose PURPOSE is served by a connected page: a live session is sent there instead of seeing a notice.
 * Each target must be a real, connected route (verified by tests/mock-only-routes.test.ts). "[id]" in the target is
 * replaced by the id segment of the source URL.
 */
export const LIVE_REDIRECTS: Readonly<Record<string, string>> = {
  "/audit": "/tenant/audit",
  "/fleet/health": "/intelligence/fleet",
  "/executive": "/dashboard",
  "/maintenance/records": "/maintenance/work-orders",
  "/maintenance/tasks": "/maintenance/work-orders",
  "/maintenance/planning": "/maintenance/work-orders",
  "/maintenance/release-readiness": "/maintenance/control-center",
  "/organization/usage": "/tenant/usage",
  "/organization/roles/[id]": "/tenant/roles",
  "/organization/roles/new": "/tenant/roles",
  "/organization/users/[id]": "/tenant/users",
  "/maintenance/control-tower": "/maintenance/control-center",
  "/maintenance/hangar": "/maintenance/work-orders",
  "/maintenance/operations": "/maintenance/work-orders",
  "/platform/features": "/platform/product-catalog",
  "/evidence/[id]": "/compliance/evidence/[id]",
};

function toRegex(pattern: string): RegExp {
  const source = pattern
    .split("/")
    .map((seg) => (/^\[.+\]$/.test(seg) ? "[^/]+" : seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("/");
  return new RegExp("^" + source + "/?$");
}

const COMPILED = [...MOCK_ONLY_ROUTES, ...SAMPLE_SECTION_ROUTES].map((pattern) => ({ pattern, re: toRegex(pattern) }));

/** The registered mock-only pattern matching this pathname, or null. */
export function matchMockOnlyRoute(pathname: string): string | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  for (const c of COMPILED) if (c.re.test(path)) return c.pattern;
  return null;
}

export function isMockOnlyRoute(pathname: string): boolean {
  return matchMockOnlyRoute(pathname) !== null;
}

/** Connected page a live session should be sent to for this pathname, or null when there is none. */
export function liveRedirectFor(pathname: string): string | null {
  const pattern = matchMockOnlyRoute(pathname);
  if (!pattern) return null;
  const target = LIVE_REDIRECTS[pattern];
  if (!target) return null;
  const id = pathname.replace(/\/+$/, "").split("/").pop() ?? "";
  return target.replace("[id]", id);
}
