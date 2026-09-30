// Pages that render ONLY bundled sample data (no live-API code path and no demo gate).
//
// A real (non-demo) session must never see fabricated records presented as its own, so RouteEntitlementGuard replaces
// these routes with a "not connected to live data" notice. Demo sessions keep the sample-data pages. The list is
// verified against the filesystem by tests/mock-only-routes.test.ts: adding a page that imports lib/mock|lib/demo
// without a live-API path or a demo gate fails that test until the page is either connected to the API (preferred) or
// registered here. Remove a route from this list when its page is wired to the backend.

export const MOCK_ONLY_ROUTES: readonly string[] = [
  "/aircraft/[id]/configuration",
  "/assessments",
  "/assessments/[id]",
  "/assessments/[id]/review",
  "/audit",
  "/automation",
  "/compliance/pre-audit",
  "/components",
  "/components/[id]",
  "/documents",
  "/engines",
  "/engines/[id]",
  "/evidence",
  "/evidence/[id]",
  "/executive",
  "/finance",
  "/finance/[id]",
  "/fleet/aircraft/[id]/health",
  "/fleet/health",
  "/integrations",
  "/maintenance-program",
  "/maintenance/defects",
  "/maintenance/discrepancies",
  "/maintenance/material-readiness",
  "/maintenance/parts/[id]",
  "/maintenance/planning",
  "/maintenance/planning/[id]",
  "/maintenance/projects",
  "/maintenance/projects/[id]",
  "/maintenance/projects/[id]/intelligence",
  "/maintenance/records",
  "/maintenance/release-readiness",
  "/maintenance/tasks",
  "/notifications",
  "/organization/readiness",
  "/organization/roles/[id]",
  "/organization/roles/new",
  "/organization/usage",
  "/organization/users/[id]",
  "/pilot",
  "/platform/features",
  "/procurement",
  "/procurement/approvals",
  "/procurement/approvals/[id]",
  "/procurement/cart",
  "/procurement/parts",
  "/procurement/purchase-orders/[id]",
  "/procurement/vendors",
  "/procurement/vendors/[id]",
  "/regulations",
  "/regulations/[id]",
  "/reports",
  "/reports/[id]",
  "/workspace",
];

/** Where a customer can find live data for the same purpose, when a connected page exists. */
export const LIVE_EQUIVALENT: Readonly<Record<string, { href: string; label: string }>> = {
  "/audit": { href: "/tenant/audit", label: "Audit Trail" },
  "/fleet/health": { href: "/intelligence/fleet", label: "Fleet Intelligence" },
  "/executive": { href: "/dashboard", label: "Dashboard" },
  "/maintenance/records": { href: "/maintenance/work-orders", label: "Work Orders" },
  "/maintenance/tasks": { href: "/maintenance/work-orders", label: "Work Orders" },
  "/maintenance/planning": { href: "/maintenance/operations", label: "Maintenance Operations" },
  "/maintenance/release-readiness": { href: "/maintenance/control-center", label: "Maintenance Control Center" },
  "/assessments": { href: "/assessment-intelligence", label: "Assessment Intelligence" },
  "/procurement": { href: "/procurement/purchase-orders", label: "Purchase Orders" },
  "/organization/usage": { href: "/tenant/usage", label: "Usage" },
};

function toRegex(pattern: string): RegExp {
  const source = pattern
    .split("/")
    .map((seg) => (/^\[.+\]$/.test(seg) ? "[^/]+" : seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("/");
  return new RegExp("^" + source + "/?$");
}

const COMPILED = MOCK_ONLY_ROUTES.map((pattern) => ({ pattern, re: toRegex(pattern) }));

/** The registered mock-only pattern matching this pathname, or null. */
export function matchMockOnlyRoute(pathname: string): string | null {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  for (const c of COMPILED) if (c.re.test(path)) return c.pattern;
  return null;
}

export function isMockOnlyRoute(pathname: string): boolean {
  return matchMockOnlyRoute(pathname) !== null;
}
