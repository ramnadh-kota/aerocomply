import { describe, it, expect } from "vitest";
import { NAV_FEATURE_MAP, isNavItemEntitlementGated } from "../lib/entitlements/navFeatureMap";
import { NAV_GROUPS, type NavGroup } from "../components/layout/Sidebar";

// M21.6 — verifies the fix for the mismatch M21.5 found and reported (not
// fixed) in M21_5_REPORT.md Section I: NAV_FEATURE_MAP previously used
// speculative FEATURE_* strings that matched no real backend
// ProductFeature.code. As of M21.6 the only three real feature_key values
// are the ones seeded by backend/scripts/seed_product_catalog.py --
// duplicated here as a literal list (not imported, since this is a
// frontend-only test file with no access to the Python seed script) so a
// future change to either side that breaks the correspondence is caught.
// If the backend catalog ever gains/removes a feature, update this list
// deliberately alongside seed_product_catalog.py.
const REAL_BACKEND_FEATURE_KEYS = [
  "work_order_management",
  "drone_fleet_management",
  "procurement_management",
];

function allHrefs(groups: NavGroup[]): string[] {
  return groups.flatMap((g) => g.items.map((i) => i.href));
}

describe("NAV_FEATURE_MAP (M21.6 backend-key correction)", () => {
  it("every mapped value is a real backend feature_key, never a speculative FEATURE_* string", () => {
    for (const [href, featureKey] of Object.entries(NAV_FEATURE_MAP)) {
      expect(REAL_BACKEND_FEATURE_KEYS, `href ${href} maps to unknown key ${featureKey}`).toContain(featureKey);
    }
  });

  it("every mapped href still exists in the real tenant nav", () => {
    const hrefs = allHrefs(NAV_GROUPS);
    for (const href of Object.keys(NAV_FEATURE_MAP)) {
      expect(hrefs, `mapped href ${href} is not a real nav item`).toContain(href);
    }
  });

  it("no longer contains any of the M21.4 speculative FEATURE_* identifiers", () => {
    const values = Object.values(NAV_FEATURE_MAP);
    for (const value of values) {
      expect(value.startsWith("FEATURE_")).toBe(false);
    }
  });

  it("maps /drones to drone_fleet_management (M21.4 gap: real backend feature, no nav entry at all)", () => {
    expect(NAV_FEATURE_MAP["/drones"]).toBe("drone_fleet_management");
  });

  it("maps work orders and procurement routes to their real backend keys", () => {
    expect(NAV_FEATURE_MAP["/maintenance/work-orders"]).toBe("work_order_management");
    expect(NAV_FEATURE_MAP["/procurement"]).toBe("procurement_management");
    expect(NAV_FEATURE_MAP["/procurement/purchase-orders"]).toBe("procurement_management");
  });
});

describe("isNavItemEntitlementGated (real feature_key semantics)", () => {
  it("gates a mapped nav item when the backend explicitly reports its real feature_key as disabled", () => {
    const effectiveFeatures = { work_order_management: false };
    expect(isNavItemEntitlementGated("/maintenance/work-orders", effectiveFeatures)).toBe(true);
  });

  it("does not gate when the real feature_key is enabled", () => {
    const effectiveFeatures = { work_order_management: true };
    expect(isNavItemEntitlementGated("/maintenance/work-orders", effectiveFeatures)).toBe(false);
  });

  it("does not gate a route with no ProductFeature yet (e.g. /aircraft), even with an empty resolution", () => {
    expect(isNavItemEntitlementGated("/aircraft", {})).toBe(false);
    expect(isNavItemEntitlementGated("/compliance", { work_order_management: false })).toBe(false);
  });

  it("fails open (not gated) when effectiveFeatures is null/undefined, e.g. NO_SUBSCRIPTION resolution", () => {
    expect(isNavItemEntitlementGated("/maintenance/work-orders", null)).toBe(false);
    expect(isNavItemEntitlementGated("/maintenance/work-orders", undefined)).toBe(false);
  });

  it("does not gate when the feature key is simply absent from the resolution map (not explicitly false)", () => {
    expect(isNavItemEntitlementGated("/drones", { work_order_management: false })).toBe(false);
  });
});
