import { describe, it, expect } from "vitest";
import {
  canonicalizeFeatureKey,
  hasFeatureKey,
  dedupeEffectiveFeatures,
  FEATURE_KEYS,
  DEFAULT_ON_FEATURES,
} from "../lib/entitlements/featureKeys";
import {
  getRouteFeatureKey,
  isNavItemUnavailable,
  isNavItemEntitlementGated,
} from "../lib/entitlements/navFeatureMap";
import { isSuiteAllowed } from "../components/auth/SuiteGuard";
import { getDemoOrganizationEntitlements } from "../lib/demo/demoPlatform";

describe("Organisation Portal Entitlement Resolution", () => {
  it("canonicalizes all asset fleet feature keys and legacy aliases", () => {
    expect(canonicalizeFeatureKey("aircraft_fleet_management")).toBe(FEATURE_KEYS.AIRCRAFT_FLEET_MANAGEMENT);
    expect(canonicalizeFeatureKey("aircraft_fleet")).toBe(FEATURE_KEYS.AIRCRAFT_FLEET_MANAGEMENT);
    expect(canonicalizeFeatureKey("drone_fleet_management")).toBe(FEATURE_KEYS.DRONE_FLEET_MANAGEMENT);
    expect(canonicalizeFeatureKey("drone_operations")).toBe(FEATURE_KEYS.DRONE_FLEET_MANAGEMENT);
    expect(canonicalizeFeatureKey("helicopter_fleet_management")).toBe(FEATURE_KEYS.HELICOPTER_FLEET_MANAGEMENT);
    expect(canonicalizeFeatureKey("evtol_fleet_management")).toBe(FEATURE_KEYS.EVTOL_FLEET_MANAGEMENT);
    expect(canonicalizeFeatureKey("compliance_reporting")).toBe(FEATURE_KEYS.COMPLIANCE_MANAGEMENT);
    expect(canonicalizeFeatureKey("maintenance_inspections")).toBe(FEATURE_KEYS.INSPECTIONS_MANAGEMENT);
  });

  it("resolves multi-suite access correctly in SuiteGuard", () => {
    // Multi-suite tenant holds MULTI_SUITE code and active suite codes [AIRCRAFT, DRONE_UAV]
    expect(isSuiteAllowed(["AIRCRAFT"], "MULTI_SUITE", ["AIRCRAFT", "DRONE_UAV"])).toBe(true);
    expect(isSuiteAllowed(["DRONE_UAV"], "MULTI_SUITE", ["AIRCRAFT", "DRONE_UAV"])).toBe(true);
    expect(isSuiteAllowed(["HELICOPTER"], "MULTI_SUITE", ["AIRCRAFT", "DRONE_UAV"])).toBe(false);

    // Single suite tenant
    expect(isSuiteAllowed(["AIRCRAFT"], "AIRCRAFT", ["AIRCRAFT"])).toBe(true);
    expect(isSuiteAllowed(["DRONE_UAV"], "AIRCRAFT", ["AIRCRAFT"])).toBe(false);
  });

  it("demo organization provides full multi-suite capabilities and canonical features", () => {
    const demo = getDemoOrganizationEntitlements("00000000-0000-0000-0000-000000000001");
    expect(demo.resolution_status).toBe("ACTIVE");
    expect(demo.suite_code).toBe("MULTI_SUITE");
    expect(demo.active_suites?.map((s) => s.suite_code)).toContain("AIRCRAFT");
    expect(demo.active_suites?.map((s) => s.suite_code)).toContain("DRONE_UAV");

    // Canonical features must be present
    expect(hasFeatureKey(demo.effective_features, "aircraft_fleet_management")).toBe(true);
    expect(hasFeatureKey(demo.effective_features, "drone_fleet_management")).toBe(true);
    expect(hasFeatureKey(demo.effective_features, "work_order_management")).toBe(true);
    expect(hasFeatureKey(demo.effective_features, "compliance_management")).toBe(true);
    expect(hasFeatureKey(demo.effective_features, "inspections_management")).toBe(true);
  });

  it("evaluates navigation availability against active entitlements", () => {
    const effective = {
      aircraft_fleet_management: true,
      work_order_management: true,
      compliance_management: true,
      drone_fleet_management: false,
    };
    const hasFeature = (key: string) => hasFeatureKey(effective, key);

    expect(isNavItemUnavailable("/aircraft", hasFeature)).toBe(false);
    expect(isNavItemUnavailable("/maintenance/work-orders", hasFeature)).toBe(false);
    expect(isNavItemUnavailable("/compliance", hasFeature)).toBe(false);
    expect(isNavItemUnavailable("/drones", hasFeature)).toBe(true);
    expect(isNavItemUnavailable("/drone-ops/overview", hasFeature)).toBe(true);
  });

  it("handles case-insensitive and uppercase effective feature maps from backend", () => {
    const backendEffective = {
      AIRCRAFT_FLEET_MANAGEMENT: true,
      WORK_ORDER_MANAGEMENT: true,
      COMPLIANCE_MANAGEMENT: false,
    };
    expect(hasFeatureKey(backendEffective, "aircraft_fleet_management")).toBe(true);
    expect(hasFeatureKey(backendEffective, "work_order_management")).toBe(true);
    expect(hasFeatureKey(backendEffective, "compliance_management")).toBe(false);
  });

  it("dedupes effective features cleanly without duplicate entries", () => {
    const effective = {
      drone_fleet_management: true,
      DRONE_FLEET_MANAGEMENT: true,
      drone_operations: true,
      aircraft_fleet_management: true,
      AIRCRAFT_FLEET_MANAGEMENT: true,
    };
    const deduped = dedupeEffectiveFeatures(effective);
    const keys = deduped.map(([k]) => k);
    expect(keys.filter((k) => k === "drone_fleet_management").length).toBe(1);
    expect(keys.filter((k) => k === "aircraft_fleet_management").length).toBe(1);
  });
});
