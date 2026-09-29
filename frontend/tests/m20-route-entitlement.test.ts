import { describe, it, expect } from "vitest";
import { getRouteFeatureKey } from "../lib/entitlements/navFeatureMap";
import { hasFeatureKey } from "../lib/entitlements/featureKeys";

describe("M20 route -> feature resolution", () => {
  it("maps detail routes to their section feature", () => {
    expect(getRouteFeatureKey("/aircraft")).toBe("aircraft_fleet_management");
    expect(getRouteFeatureKey("/aircraft/123")).toBe("aircraft_fleet_management");
    expect(getRouteFeatureKey("/aircraft/configuration/")).toBe("aircraft_fleet_management");
    expect(getRouteFeatureKey("/drones/abc")).toBe("drone_fleet_management");
  });

  it("uses the longest matching prefix", () => {
    expect(getRouteFeatureKey("/maintenance/inspections/9")).toBe("inspections_management");
    expect(getRouteFeatureKey("/maintenance/work-orders")).toBe("work_order_management");
  });

  it("does not gate unmapped routes or prefix look-alikes", () => {
    expect(getRouteFeatureKey("/dashboard")).toBeNull();
    expect(getRouteFeatureKey("/aircraftx")).toBeNull();
  });
});

describe("M20 disabled feature behaviour", () => {
  it("an override-disabled feature is denied even if a legacy alias is absent", () => {
    const effective = { drone_fleet_management: true, battery_analytics: false };
    expect(hasFeatureKey(effective, "battery_analytics")).toBe(false);
    expect(hasFeatureKey(effective, "aircraft_fleet_management")).toBe(false);
    expect(hasFeatureKey(effective, "drone_operations")).toBe(true);
  });
});

describe("M20 baseline (default-on) features mirror the backend", () => {
  it("audit_logging / release_readiness are on unless explicitly disabled", () => {
    expect(hasFeatureKey({ drone_fleet_management: true }, "audit_logging")).toBe(true);
    expect(hasFeatureKey({ drone_fleet_management: true }, "release_readiness")).toBe(true);
    expect(hasFeatureKey({ audit_logging: false }, "audit_logging")).toBe(false);
    expect(hasFeatureKey({ battery_analytics: true }, "predictive_maintenance")).toBe(false);
  });
});
