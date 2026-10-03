import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { LIVE_REDIRECTS, MOCK_ONLY_ROUTES, SAMPLE_SECTION_ROUTES, isMockOnlyRoute, isNavItemNotConnected, liveRedirectFor, matchMockOnlyRoute } from "../lib/mock-only-routes";

const APP = join(__dirname, "..", "app", "(app)");

function pages(dir: string, prefix = ""): { route: string; source: string }[] {
  const out: { route: string; source: string }[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...pages(full, `${prefix}/${name}`));
    else if (name === "page.tsx") out.push({ route: prefix || "/", source: readFileSync(full, "utf-8") });
  }
  return out;
}

/** Same rule as the registry's header comment: sample data, no live-API path, no demo gate. */
function isMockOnly(source: string): boolean {
  const mock = /from "@\/lib\/(mock|demo)\//.test(source);
  const live = /from "@\/lib\/api\/|apiRequest|Api\./.test(source);
  const gated = /isDemo|sessionType|useDataMode|DataMode|withLive\(/.test(source);
  return mock && !live && !gated;
}

describe("mock-only route registry", () => {
  const scanned = pages(APP).filter((p) => isMockOnly(p.source)).map((p) => p.route).sort();

  it("lists exactly the pages that only contain sample data", () => {
    expect([...MOCK_ONLY_ROUTES].sort()).toEqual(scanned);
  });

  it("matches concrete URLs, including dynamic segments and trailing slashes", () => {
    expect(isMockOnlyRoute("/finance")).toBe(true);
    expect(isMockOnlyRoute("/evidence/abc-123")).toBe(true);
    expect(isMockOnlyRoute("/evidence/abc-123/")).toBe(true);
    expect(matchMockOnlyRoute("/finance/42")).toBe("/finance/[id]");
    expect(isMockOnlyRoute("/maintenance/projects/9/intelligence")).toBe(true);
  });

  it("does not match connected pages or unrelated prefixes", () => {
    for (const live of ["/dashboard", "/drones", "/drones/1", "/maintenance/work-orders", "/tenant/audit", "/data-sources",
      "/helicopters", "/evtols", "/evidence-files", "/procurement/purchase-orders", "/evidence", "/components", "/engines/7", "/procurement/parts",
      "/procurement/vendors/42", "/regulations", "/assessments"]) {
      expect(isMockOnlyRoute(live), live).toBe(false);
    }
  });

  it("lists sample-section pages that exist and are not otherwise registered", () => {
    const all = new Set(pages(APP).map((p) => p.route));
    for (const route of SAMPLE_SECTION_ROUTES) {
      expect(all.has(route), route).toBe(true);
      expect(MOCK_ONLY_ROUTES).not.toContain(route);
      expect(isMockOnlyRoute(route)).toBe(true);
    }
  });

  it("only redirects to real, connected routes", () => {
    const live = new Set(pages(APP).filter((p) => !isMockOnly(p.source)).map((p) => p.route));
    const registered = new Set([...MOCK_ONLY_ROUTES, ...SAMPLE_SECTION_ROUTES]);
    for (const [from, to] of Object.entries(LIVE_REDIRECTS)) {
      expect(registered.has(from), from).toBe(true);
      expect(live.has(to) && !registered.has(to), `${from} -> ${to}`).toBe(true);
    }
  });

  it("resolves redirect targets, carrying the id segment", () => {
    expect(liveRedirectFor("/audit")).toBe("/tenant/audit");
    expect(liveRedirectFor("/evidence/abc-123")).toBe("/compliance/evidence/abc-123");
    expect(liveRedirectFor("/organization/roles/new")).toBe("/tenant/roles");
    expect(liveRedirectFor("/assessments/a1/review")).toBe("/assessments/a1");
    expect(liveRedirectFor("/fleet/aircraft/ac9/health")).toBe("/aircraft/ac9");
    expect(liveRedirectFor("/aircraft/ac9/configuration")).toBe("/aircraft/ac9");
    expect(liveRedirectFor("/maintenance/planning/wo7")).toBe("/maintenance/work-orders/wo7");
    expect(liveRedirectFor("/maintenance/discrepancies")).toBe("/maintenance/defects");
    expect(liveRedirectFor("/maintenance/material-readiness")).toBe("/maintenance/parts");
    expect(liveRedirectFor("/finance")).toBeNull();          // mock-only with no live equivalent: notice card
    expect(liveRedirectFor("/dashboard")).toBeNull();        // not mock-only at all
  });
});

describe("sidebar lock state for demo-data pages", () => {
  it("keeps routes with a live equivalent clickable (the route guard redirects them)", () => {
    for (const href of ["/audit", "/fleet/health", "/maintenance/tasks", "/maintenance/release-readiness", "/executive", "/documents"]) {
      expect(isMockOnlyRoute(href), href).toBe(true);
      expect(isNavItemNotConnected(href), href).toBe(false);
    }
  });

  it("still locks demo-only pages that have no live equivalent", () => {
    for (const href of ["/pilot", "/automation", "/finance", "/reports", "/workspace", "/organization/readiness"]) {
      expect(isNavItemNotConnected(href), href).toBe(true);
    }
  });

  it("never locks a connected page", () => {
    for (const href of ["/dashboard", "/maintenance/work-orders", "/tenant/audit", "/drones"]) {
      expect(isNavItemNotConnected(href), href).toBe(false);
    }
  });
});
