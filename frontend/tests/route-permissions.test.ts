import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { ROUTE_PERMISSIONS, getRoutePermissions, isRouteForbidden } from "../lib/rbac/routePermissions";
import { NAV_GROUPS } from "../components/layout/Sidebar";

// Parse the backend catalog so the map can never reference a permission the API does not define.
const py = readFileSync(join(__dirname, "..", "..", "backend", "app", "core", "permissions.py"), "utf8");
const BACKEND_PERMISSIONS = new Set([...py.matchAll(/^\s+[A-Z_]+ = "([a-z_]+:[a-z_]+)"/gm)].map((m) => m[1]));

const PERMISSION_VALUE = new Map([...py.matchAll(/^\s+([A-Z_]+) = "([a-z_]+:[a-z_]+)"/gm)].map((m) => [m[1], m[2]]));

// Effective permission sets, parsed from ROLE_PERMISSIONS so the test follows the real role table.
function rolePermissions(role: string): string[] {
  const start = py.indexOf(`Role.${role}: {`);
  const end = py.indexOf("},", start);
  return [...py.slice(start, end).matchAll(/Permission\.([A-Z_]+)/g)].map((m) => PERMISSION_VALUE.get(m[1])!);
}

describe("ROUTE_PERMISSIONS", () => {
  it("only references permissions that exist in the backend catalog", () => {
    expect(BACKEND_PERMISSIONS.size).toBeGreaterThan(20);
    for (const [route, perms] of Object.entries(ROUTE_PERMISSIONS)) {
      for (const p of perms) expect(BACKEND_PERMISSIONS, `${route} -> ${p}`).toContain(p);
    }
  });

  it("uses longest-prefix matching so a specific route overrides its section", () => {
    expect(getRoutePermissions("/maintenance/work-orders")).toEqual(["aircraft:read"]);
    expect(getRoutePermissions("/maintenance/parts")).toEqual(["part:read"]);
    expect(getRoutePermissions("/maintenance/parts/123")).toEqual(["part:read"]);
    expect(getRoutePermissions("/dashboard")).toBeNull();
  });
});

describe("isRouteForbidden", () => {
  it("never denies when permissions are unknown (loading / older API) -- the backend still enforces", () => {
    expect(isRouteForbidden("/tenant/users", undefined)).toBe(false);
    expect(isRouteForbidden("/tenant/users", null)).toBe(false);
  });

  it("matches the role matrix for the existing tenant roles", () => {
    const viewer = rolePermissions("VIEWER");
    const engineer = rolePermissions("MAINTENANCE_ENGINEER");
    const orgAdmin = rolePermissions("ORG_ADMIN");
    const camo = rolePermissions("CAMO_MANAGER");
    const compliance = rolePermissions("COMPLIANCE_MANAGER");

    // ORG_ADMIN: administration and data import
    expect(isRouteForbidden("/tenant/users", orgAdmin)).toBe(false);
    expect(isRouteForbidden("/data-import", orgAdmin)).toBe(false);
    // Fleet Manager-type role (CAMO_MANAGER): operations yes, user administration no
    expect(isRouteForbidden("/maintenance/work-orders", camo)).toBe(false);
    expect(isRouteForbidden("/procurement", camo)).toBe(false);
    expect(isRouteForbidden("/tenant/users", camo)).toBe(true);
    // Maintenance engineer: work orders and parts yes; admin, audit and data import no
    expect(isRouteForbidden("/maintenance/work-orders", engineer)).toBe(false);
    expect(isRouteForbidden("/maintenance/parts", engineer)).toBe(false);
    expect(isRouteForbidden("/tenant/users", engineer)).toBe(true);
    expect(isRouteForbidden("/tenant/audit", engineer)).toBe(true);
    expect(isRouteForbidden("/data-import", engineer)).toBe(true);
    // Read-only viewer: can read fleet, cannot administer or run assessments' writes / audit
    expect(isRouteForbidden("/aircraft", viewer)).toBe(false);
    expect(isRouteForbidden("/tenant/users", viewer)).toBe(true);
    expect(isRouteForbidden("/audit", viewer)).toBe(true);
    expect(isRouteForbidden("/data-import", viewer)).toBe(true);
    // Compliance manager keeps audit and compliance
    expect(isRouteForbidden("/audit", compliance)).toBe(false);
    expect(isRouteForbidden("/compliance", compliance)).toBe(false);
  });

  it("every mapped route that is a sidebar item resolves for ORG_ADMIN (no admin locked out of its own nav)", () => {
    const orgAdmin = rolePermissions("ORG_ADMIN");
    const hrefs = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.href));
    for (const href of hrefs) expect(isRouteForbidden(href, orgAdmin), href).toBe(false);
  });
});
