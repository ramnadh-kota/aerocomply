import { describe, it, expect } from "vitest";
import {
  DEMO_DRONES,
  DEMO_BATTERIES,
  DEMO_COMPONENTS,
  DEMO_FLIGHTS,
  DEMO_FINDINGS,
  DEMO_MISSIONS,
  DEMO_COMPLIANCE_ASSESSMENTS,
  getDemoDrones,
  getDemoDroneById,
  getDemoBatteryForDrone,
  getDemoComponentsForDrone,
  getDemoFlightsForDrone,
  getDemoUtilizationForDrone,
  getDemoFindingsForDrone,
  getDemoMaintenanceForDrone,
  getDemoMissionsForDrone,
  getDemoDeploymentReadiness,
  getDemoComplianceForDrone,
  getDemoFleetStatistics,
} from "../lib/demo/demoDrones";
import { DEMO_ORG_ID } from "../lib/auth/SessionContext";

describe("Synthetic Drone Operations Demo Dataset", () => {
  it("contains exactly 6 deterministic synthetic drones belonging to DEMO_ORG_ID", () => {
    const drones = getDemoDrones();
    expect(drones).toHaveLength(6);
    expect(drones.map((d) => d.registration)).toEqual([
      "KOTA-D001",
      "KOTA-D002",
      "KOTA-D003",
      "KOTA-D004",
      "KOTA-D005",
      "KOTA-D006",
    ]);

    for (const drone of drones) {
      expect(drone.organization_id).toBe(DEMO_ORG_ID);
      expect(drone.asset_type).toBe("DRONE");
      expect(drone.serial_number).toBeTruthy();
      expect(drone.manufacturer).toBeTruthy();
      expect(drone.model).toBeTruthy();
    }
  });

  it("resolves drone by both synthetic ID and registration", () => {
    const droneById = getDemoDroneById("drn-kota-001");
    const droneByReg = getDemoDroneById("KOTA-D001");

    expect(droneById).toBeDefined();
    expect(droneByReg).toBeDefined();
    expect(droneById?.id).toBe(droneByReg?.id);
    expect(droneById?.registration).toBe("KOTA-D001");
  });

  it("calculates fleet statistics accurately and dynamically from data", () => {
    const stats = getDemoFleetStatistics();
    expect(stats.totalDrones).toBe(6);
    expect(stats.groundedDrones).toBe(1); // KOTA-D005 is GROUNDED
    expect(stats.readyDrones).toBe(4); // D001, D002, D004, D006 are READY
    expect(stats.blockedDrones).toBe(2); // D003, D005 are BLOCKED
    expect(stats.maintenanceDueDrones).toBe(1); // D003 has OVERDUE maintenance
    expect(stats.openFindingsCount).toBe(2); // D003 and D005 have OPEN findings
    expect(stats.totalFlights).toBe(DEMO_FLIGHTS.length);
    expect(Number(stats.totalFlightHours)).toBeGreaterThan(0);
  });

  it("correctly evaluates deployment readiness for READY drones", () => {
    const readinessD1 = getDemoDeploymentReadiness("drn-kota-001");
    expect(readinessD1.status).toBe("READY");
    expect(readinessD1.blockers).toHaveLength(0);

    const readinessD2 = getDemoDeploymentReadiness("drn-kota-002");
    expect(readinessD2.status).toBe("READY");
    expect(readinessD2.blockers).toHaveLength(0);

    const readinessD4 = getDemoDeploymentReadiness("drn-kota-004");
    expect(readinessD4.status).toBe("READY");
    expect(readinessD4.blockers).toHaveLength(0);

    const readinessD6 = getDemoDeploymentReadiness("drn-kota-006");
    expect(readinessD6.status).toBe("READY");
    expect(readinessD6.blockers).toHaveLength(0);
  });

  it("correctly evaluates deployment readiness for BLOCKED drones with detailed blocker reasons", () => {
    // KOTA-D003 has overdue maintenance and an open finding
    const readinessD3 = getDemoDeploymentReadiness("drn-kota-003");
    expect(readinessD3.status).toBe("BLOCKED");
    expect(readinessD3.blockers).toContain("Maintenance overdue");
    expect(readinessD3.blockers.some((b) => b.includes("Unresolved finding"))).toBe(true);

    // KOTA-D005 is grounded, has a critical battery, and an open finding
    const readinessD5 = getDemoDeploymentReadiness("drn-kota-005");
    expect(readinessD5.status).toBe("BLOCKED");
    expect(readinessD5.blockers).toContain("Drone is not active (status: GROUNDED)");
    expect(readinessD5.blockers).toContain("Battery critical");
    expect(readinessD5.blockers.some((b) => b.includes("Unresolved finding"))).toBe(true);
  });

  it("resolves installed batteries and component configurations coherently", () => {
    for (const drone of DEMO_DRONES) {
      const battery = getDemoBatteryForDrone(drone.id);
      expect(battery).toBeDefined();
      expect(battery?.asset_id).toBe(drone.id);

      const components = getDemoComponentsForDrone(drone.id);
      expect(components.length).toBeGreaterThan(0);
      for (const component of components) {
        expect(component.asset_id).toBe(drone.id);
      }
    }
  });

  it("computes flight utilization consistently across flights", () => {
    const utilizationD1 = getDemoUtilizationForDrone("drn-kota-001");
    const flightsD1 = getDemoFlightsForDrone("drn-kota-001");

    expect(utilizationD1.total_flights).toBe(flightsD1.length);
    expect(utilizationD1.total_minutes).toBe(
      flightsD1.reduce((sum, f) => sum + f.duration_minutes, 0)
    );
    expect(utilizationD1.total_cycles).toBe(
      flightsD1.reduce((sum, f) => sum + f.cycles, 0)
    );
  });

  it("provides coherent scheduled missions with full pre-flight check matrix", () => {
    for (const mission of DEMO_MISSIONS) {
      expect(mission.asset_id).toBeTruthy();
      expect(mission.pilot_name).toBeTruthy();
      expect(mission.operating_area).toBeTruthy();
      expect(mission.preflight_checks).toHaveProperty("airframe_condition");
      expect(mission.preflight_checks).toHaveProperty("battery_state");
      expect(mission.preflight_checks).toHaveProperty("maintenance_status");
      expect(mission.preflight_checks).toHaveProperty("inspection_clearance");
      expect(mission.preflight_checks).toHaveProperty("open_findings");
      expect(mission.preflight_checks).toHaveProperty("pilot_qualification");
      expect(mission.preflight_checks).toHaveProperty("airspace_authorization");

      if (mission.overall_preflight === "BLOCKED") {
        expect(mission.blockers.length).toBeGreaterThan(0);
      } else {
        expect(mission.overall_preflight).toBe("READY");
      }
    }
  });

  it("resolves deterministic asset-scoped compliance determinations for synthetic drones", () => {
    expect(DEMO_COMPLIANCE_ASSESSMENTS.length).toBeGreaterThan(0);

    for (const asmt of DEMO_COMPLIANCE_ASSESSMENTS) {
      expect(asmt.organization_id).toBe(DEMO_ORG_ID);
      expect(asmt.aircraft_id).toBeNull();
      expect(asmt.asset_id).toBeTruthy();
      expect(asmt.requirement_number).toBeTruthy();
      expect(asmt.authority).toBeTruthy();
      expect(["COMPLIANT", "NON_COMPLIANT", "REVIEW_REQUIRED"]).toContain(asmt.status);
    }

    // Verify KOTA-D001 has compliant determinations
    const d1Compliance = getDemoComplianceForDrone("drn-kota-001");
    expect(d1Compliance.length).toBeGreaterThan(0);
    expect(d1Compliance.every((c) => c.status === "COMPLIANT")).toBe(true);

    // Verify KOTA-D002 has a non-compliant battery determination
    const d2Compliance = getDemoComplianceForDrone("drn-kota-002");
    expect(d2Compliance.some((c) => c.status === "NON_COMPLIANT")).toBe(true);

    // Verify KOTA-D005 has non-compliant airframe determination
    const d5Compliance = getDemoComplianceForDrone("drn-kota-005");
    expect(d5Compliance.some((c) => c.status === "NON_COMPLIANT")).toBe(true);
  });
});
