import { describe, it, expect } from "vitest";
import {
  DEMO_ASSETS,
  getDemoAssetDetail,
  getDemoConfiguration,
  getDemoOperations,
  getDemoMaintenance,
  getDemoInspections,
  getDemoEvidence,
  getDemoFindings,
  getDemoCompliance,
  getDemoReadiness,
  getDemoHistory,
  getDemoDomainContext,
} from "../lib/demo/demoAssets";

describe("M4: Common Aerospace Domain Foundation (Frontend Contracts & Demo)", () => {
  it("spans the full aerospace asset spectrum (Fixed-Wing, Drones, Helicopters, eVTOL)", () => {
    const types = new Set(DEMO_ASSETS.map((a) => a.asset_type));
    expect(types.has("AIRCRAFT")).toBe(true);
    expect(types.has("DRONE")).toBe(true);
    expect(types.has("HELICOPTER")).toBe(true);
    expect(types.has("EVTOL")).toBe(true);
  });

  it("every demo asset has standard identity fields", () => {
    for (const asset of DEMO_ASSETS) {
      expect(asset.id).toBeDefined();
      expect(asset.organization_id).toBe("demo-org-id");
      expect(asset.registration).toBeTruthy();
      expect(asset.status).toBeTruthy();
      expect(asset.created_at).toBeTruthy();
    }
  });

  it("resolves domain-appropriate configuration slots for Helicopter", () => {
    const heli = DEMO_ASSETS.find((a) => a.asset_type === "HELICOPTER")!;
    expect(heli).toBeDefined();
    const config = getDemoConfiguration(heli.id);
    expect(config.asset_type).toBe("HELICOPTER");
    expect(config.slots.some((s) => s.slot_name.includes("Turboshaft Engine"))).toBe(true);
    expect(config.slots.some((s) => s.slot_name.includes("Transmission"))).toBe(true);
    expect(config.airframe_spec.rotor_system).toBeDefined();
  });

  it("resolves domain-appropriate configuration slots for Drone", () => {
    const drone = DEMO_ASSETS.find((a) => a.asset_type === "DRONE")!;
    expect(drone).toBeDefined();
    const config = getDemoConfiguration(drone.id);
    expect(config.asset_type).toBe("DRONE");
    expect(config.slots.some((s) => s.slot_name.includes("Flight Controller"))).toBe(true);
    expect(config.slots.some((s) => s.slot_name.includes("Propulsion Motor"))).toBe(true);
    expect(config.slots.some((s) => s.slot_name.includes("Sensor / Camera Payload"))).toBe(true);
  });

  it("resolves domain-appropriate configuration slots for Fixed-Wing Aircraft", () => {
    const plane = DEMO_ASSETS.find((a) => a.asset_type === "AIRCRAFT")!;
    expect(plane).toBeDefined();
    const config = getDemoConfiguration(plane.id);
    expect(config.asset_type).toBe("AIRCRAFT");
    expect(config.slots.some((s) => s.slot_name.includes("Turbofan Engine"))).toBe(true);
    expect(config.slots.some((s) => s.slot_name.includes("Auxiliary Power Unit"))).toBe(true);
  });

  it("provides operational utilization metrics across flight hours, cycles, and landings", () => {
    const asset = DEMO_ASSETS[0];
    const ops = getDemoOperations(asset.id);
    expect(ops.utilization.total_flight_hours).toBeGreaterThan(0);
    expect(ops.utilization.total_cycles).toBeGreaterThan(0);
    expect(ops.utilization.metrics.length).toBeGreaterThanOrEqual(3);
    expect(ops.utilization.metrics.every((m) => m.is_metered)).toBe(true);
  });

  it("evaluates 5 distinct readiness dimensions with non-RTS legal disclaimer", () => {
    const asset = DEMO_ASSETS[0];
    const readiness = getDemoReadiness(asset.id);
    expect(readiness.overall_status).toBe("READY");
    expect(readiness.dimensions).toHaveLength(5);

    const dims = readiness.dimensions.map((d) => d.dimension);
    expect(dims).toEqual([
      "OPERATIONAL",
      "MAINTENANCE",
      "COMPLIANCE",
      "DEPLOYMENT",
      "RELEASE",
    ]);

    expect(readiness.disclaimer).toContain("Does not constitute an electronic Release to Service (RTS) signature");
  });

  it("reflects degraded readiness and active blockers when asset is in MAINTENANCE", () => {
    const maintDrone = DEMO_ASSETS.find((a) => a.status === "MAINTENANCE")!;
    expect(maintDrone).toBeDefined();
    const readiness = getDemoReadiness(maintDrone.id);
    expect(readiness.overall_status).toBe("AT_RISK");

    const operationalDim = readiness.dimensions.find((d) => d.dimension === "OPERATIONAL")!;
    expect(operationalDim.status).toBe("BLOCKED");
    expect(operationalDim.blockers.length).toBeGreaterThan(0);
  });

  it("aggregates structured domain context for future decision orchestrators", () => {
    const asset = DEMO_ASSETS[0];
    const ctx = getDemoDomainContext(asset.id);
    expect(ctx.identity.id).toBe(asset.id);
    expect(ctx.configuration).toBeDefined();
    expect(ctx.utilization).toBeDefined();
    expect(ctx.compliance).toBeDefined();
    expect(ctx.readiness).toBeDefined();
    expect(typeof ctx.open_work_orders_count).toBe("number");
    expect(typeof ctx.open_findings_count).toBe("number");
  });

  it("provides chronological domain history spanning flights, maintenance, and compliance", () => {
    const asset = DEMO_ASSETS[0];
    const history = getDemoHistory(asset.id);
    expect(history.events.length).toBeGreaterThan(0);
    const eventTypes = history.events.map((e) => e.event_type);
    expect(eventTypes).toContain("asset.flight_recorded");
    expect(eventTypes).toContain("asset.component.installed");
    expect(eventTypes).toContain("asset.compliance.assessed");
    expect(eventTypes).toContain("asset.created");
  });
});
