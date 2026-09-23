import { describe, it, expect } from "vitest";
import {
  getDemoPlatformStats,
  DEMO_PLATFORM_ORGANIZATIONS,
  DEMO_PLATFORM_FEATURES,
  DEMO_PLATFORM_PLANS,
  DEMO_PLATFORM_USERS,
  getDemoOrganization,
  getDemoOrganizationUsers,
  getDemoOrganizationSubscriptions,
  getDemoOrganizationEntitlements,
} from "../lib/demo/demoPlatform";

describe("Platform Control Plane Demo Architecture (M2)", () => {
  it("computes accurate platform dashboard KPIs across synthetic tenants", () => {
    const stats = getDemoPlatformStats();
    expect(stats.totalOrganizations).toBe(5);
    expect(stats.activeOrganizations).toBe(4);
    expect(stats.suspendedOrganizations).toBe(1);
    expect(stats.totalDrones).toBeGreaterThan(0);
    expect(stats.totalAircraft).toBeGreaterThan(0);
    expect(stats.activeSubscriptions).toBeGreaterThan(0);
    expect(stats.organizationsByPlan.length).toBeGreaterThan(0);
    expect(stats.enabledFeatureDistribution.length).toBeGreaterThan(0);
  });

  it("contains diverse aerospace vertical industries without model duplication", () => {
    const industries = DEMO_PLATFORM_ORGANIZATIONS.map((o) => o.industry);
    expect(industries).toContain("DRONE_UAV");
    expect(industries).toContain("AIRCRAFT");
    expect(industries).toContain("EVTOL_AAM");
  });

  it("exposes contractual system feature keys required by Section 10", () => {
    const keys = DEMO_PLATFORM_FEATURES.map((f) => f.feature_key);
    expect(keys).toContain("drone_fleet_management");
    expect(keys).toContain("work_order_management");
    expect(keys).toContain("compliance_reporting");
    expect(keys).toContain("audit_logging");
    expect(keys).toContain("release_readiness");
    expect(keys).toContain("battery_analytics");
    expect(keys).toContain("lisa_ai_copilot");
  });

  it("enforces tenant suspension at the entitlement resolution layer", () => {
    // Org C is SUSPENDED
    const suspendedOrgId = "00000000-0000-0000-0000-000000000030";
    const res = getDemoOrganizationEntitlements(suspendedOrgId);
    expect(res.resolution_status).toBe("SUSPENDED");
    expect(Object.keys(res.effective_features).length).toBe(0);
  });

  it("resolves active tier features accurately for an active tenant", () => {
    const activeOrgId = "00000000-0000-0000-0000-000000000001";
    const res = getDemoOrganizationEntitlements(activeOrgId);
    expect(res.resolution_status).toBe("ACTIVE");
    expect(res.effective_features.drone_fleet_management).toBe(true);
    expect(res.effective_features.work_order_management).toBe(true);
  });

  it("maintains strict tenant mapping across synthetic users", () => {
    const orgUsers = getDemoOrganizationUsers("00000000-0000-0000-0000-000000000020");
    for (const u of orgUsers) {
      expect(u.organization_id).toBe("00000000-0000-0000-0000-000000000020");
    }
  });
});
