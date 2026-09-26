import { describe, it, expect } from "vitest";
import { NAV_GROUPS, PLATFORM_NAV_GROUPS, isActive, type NavGroup } from "../components/layout/Sidebar";

// M21.2 — structural tests for the regrouped tenant navigation
// (frontend/components/layout/Sidebar.tsx). Following this repo's existing
// convention (see tests/finding-detail.test.ts, tests/drone-findings-panel.test.ts)
// of testing the real data/contract a component uses rather than mounting
// components (no React Testing Library is configured in this repo).
//
// Covers: the new 7-group tenant IA exists with the expected groups and no
// duplicate/missing hrefs versus the pre-M21.2 flat set, the separate
// Platform Control Plane nav is untouched, and isActive()'s exact/prefix
// active-route matching behaves correctly for both static list routes and
// dynamic detail routes (e.g. /drones/[id]) which are intentionally NOT
// listed as their own nav items but must still resolve their parent list
// item as active.

const EXPECTED_TENANT_GROUP_LABELS = [
  "Operations",
  "Assets",
  "MRO",
  "Inspection & Evidence",
  "Compliance",
  "Resources",
  "Administration",
];

function allHrefs(groups: NavGroup[]): string[] {
  return groups.flatMap((g) => g.items.map((i) => i.href));
}

describe("Sidebar NAV_GROUPS (M21.2 IA regrouping)", () => {
  it("has exactly the 7 workflow-based groups, in order", () => {
    expect(NAV_GROUPS.map((g) => g.label)).toEqual(EXPECTED_TENANT_GROUP_LABELS);
  });

  it("has no duplicate hrefs across groups", () => {
    const hrefs = allHrefs(NAV_GROUPS);
    const unique = new Set(hrefs);
    expect(unique.size).toBe(hrefs.length);
  });

  it("every item has a non-empty href, label, and glyph", () => {
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        expect(item.href.startsWith("/")).toBe(true);
        expect(item.label.length).toBeGreaterThan(0);
        expect(item.glyph.length).toBeGreaterThan(0);
      }
    }
  });

  it("includes the three previously-orphaned routes with a real nav entry", () => {
    const hrefs = allHrefs(NAV_GROUPS);
    expect(hrefs).toContain("/organization/readiness");
    expect(hrefs).toContain("/compliance/pre-audit");
    expect(hrefs).toContain("/compliance/regulatory-register");
  });

  it("places core asset routes (Fleet Registry, Aircraft, Drones) in the Assets group, not scattered across Fleet/Overview", () => {
    const assets = NAV_GROUPS.find((g) => g.label === "Assets")!;
    const hrefs = assets.items.map((i) => i.href);
    expect(hrefs).toEqual(expect.arrayContaining(["/assets", "/aircraft", "/drones", "/engines", "/components", "/facilities"]));
  });

  it("places Inspections and Evidence together in a dedicated Inspection & Evidence group", () => {
    const group = NAV_GROUPS.find((g) => g.label === "Inspection & Evidence")!;
    const hrefs = group.items.map((i) => i.href);
    expect(hrefs).toContain("/maintenance/inspections");
    expect(hrefs).toContain("/evidence");
  });

  it("includes all M3 tenant administration routes in the Administration group", () => {
    const adminGroup = NAV_GROUPS.find((g) => g.label === "Administration")!;
    const hrefs = adminGroup.items.map((i) => i.href);
    expect(hrefs).toContain("/tenant/dashboard");
    expect(hrefs).toContain("/tenant/profile");
    expect(hrefs).toContain("/tenant/users");
    expect(hrefs).toContain("/tenant/roles");
    expect(hrefs).toContain("/tenant/invitations");
    expect(hrefs).toContain("/tenant/teams");
    expect(hrefs).toContain("/tenant/facilities");
    expect(hrefs).toContain("/tenant/fleet");
    expect(hrefs).toContain("/tenant/subscription");
    expect(hrefs).toContain("/tenant/entitlements");
    expect(hrefs).toContain("/tenant/usage");
    expect(hrefs).toContain("/tenant/audit");
    expect(hrefs).toContain("/tenant/settings");
  });

  it("has exactly 65 total tenant nav items across all 7 groups (including M4 /assets)", () => {
    expect(allHrefs(NAV_GROUPS).length).toBe(65);
  });
});

describe("PLATFORM_NAV_GROUPS (M2 Platform Control Plane)", () => {
  it("has exactly one 'Platform Control Plane' group with 15 control plane items", () => {
    expect(PLATFORM_NAV_GROUPS).toHaveLength(1);
    expect(PLATFORM_NAV_GROUPS[0].label).toBe("Platform Control Plane");
    expect(PLATFORM_NAV_GROUPS[0].items).toHaveLength(15);
    const hrefs = PLATFORM_NAV_GROUPS[0].items.map((i) => i.href);
    expect(hrefs).toContain("/platform/dashboard");
    expect(hrefs).toContain("/platform/organizations");
    expect(hrefs).toContain("/platform/users");
    expect(hrefs).toContain("/platform/subscriptions");
    expect(hrefs).toContain("/platform/plans");
    expect(hrefs).toContain("/platform/features");
    expect(hrefs).toContain("/platform/product-catalog");
    expect(hrefs).toContain("/platform/entitlements");
    expect(hrefs).toContain("/platform/provisioning");
    expect(hrefs).toContain("/platform/usage");
    expect(hrefs).toContain("/platform/deleted-records");
    expect(hrefs).toContain("/platform/audit");
    expect(hrefs).toContain("/platform/approvals");
    expect(hrefs).toContain("/platform/monitoring");
    expect(hrefs).toContain("/platform/settings");
  });
});

describe("isActive() active-route matching", () => {
  it("matches an exact static route", () => {
    expect(isActive("/drones", "/drones")).toBe(true);
    expect(isActive("/maintenance/work-orders", "/maintenance/work-orders")).toBe(true);
  });

  it("matches a dynamic detail route under a list route's nav item (e.g. /drones/[id])", () => {
    expect(isActive("/drones/44444444-4444-4444-4444-444444444444", "/drones")).toBe(true);
    expect(isActive("/aircraft/abc-123/configuration", "/aircraft")).toBe(true);
    expect(isActive("/findings/xyz", "/findings")).toBe(true);
  });

  it("does not match a sibling or unrelated route", () => {
    expect(isActive("/drones", "/aircraft")).toBe(false);
    expect(isActive("/maintenance/work-orders", "/maintenance/tasks")).toBe(false);
    // prefix-only string overlap must not false-positive (e.g. /aircraft vs /aircraft-types)
    expect(isActive("/aircraft-types", "/aircraft")).toBe(false);
  });

  it("treats /dashboard, /platform/dashboard, /tenant/dashboard, and /organization as exact-only (no accidental sub-route match)", () => {
    expect(isActive("/dashboard", "/dashboard")).toBe(true);
    expect(isActive("/dashboard/widgets", "/dashboard")).toBe(false);
    expect(isActive("/platform/dashboard", "/platform/dashboard")).toBe(true);
    expect(isActive("/platform/dashboard/stats", "/platform/dashboard")).toBe(false);
    expect(isActive("/tenant/dashboard", "/tenant/dashboard")).toBe(true);
    expect(isActive("/tenant/dashboard/kpis", "/tenant/dashboard")).toBe(false);
    expect(isActive("/organization", "/organization")).toBe(true);
    expect(isActive("/organization/users", "/organization")).toBe(false);
  });
});
