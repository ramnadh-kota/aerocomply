import { describe, it, expect } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { LIVE_EQUIVALENT, MOCK_ONLY_ROUTES, isMockOnlyRoute, matchMockOnlyRoute } from "../lib/mock-only-routes";

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
  const gated = /isDemo|sessionType|useDataMode|DataMode/.test(source);
  return mock && !live && !gated;
}

describe("mock-only route registry", () => {
  const scanned = pages(APP).filter((p) => isMockOnly(p.source)).map((p) => p.route).sort();

  it("lists exactly the pages that only contain sample data", () => {
    expect([...MOCK_ONLY_ROUTES].sort()).toEqual(scanned);
  });

  it("matches concrete URLs, including dynamic segments and trailing slashes", () => {
    expect(isMockOnlyRoute("/evidence")).toBe(true);
    expect(isMockOnlyRoute("/evidence/abc-123")).toBe(true);
    expect(isMockOnlyRoute("/evidence/abc-123/")).toBe(true);
    expect(matchMockOnlyRoute("/procurement/vendors/42")).toBe("/procurement/vendors/[id]");
    expect(isMockOnlyRoute("/maintenance/projects/9/intelligence")).toBe(true);
  });

  it("does not match connected pages or unrelated prefixes", () => {
    for (const live of ["/dashboard", "/drones", "/drones/1", "/maintenance/work-orders", "/tenant/audit", "/data-sources",
      "/helicopters", "/evtols", "/evidence-files", "/procurement/purchase-orders"]) {
      expect(isMockOnlyRoute(live), live).toBe(false);
    }
  });

  it("only points to live equivalents that are real, connected routes", () => {
    const live = new Set(pages(APP).filter((p) => !isMockOnly(p.source)).map((p) => p.route));
    for (const [from, to] of Object.entries(LIVE_EQUIVALENT)) {
      expect(MOCK_ONLY_ROUTES).toContain(from);
      expect(live.has(to.href), `${from} -> ${to.href}`).toBe(true);
    }
  });
});
