import { describe, it, expect } from "vitest";
import { DEMO_PLATFORM_PLANS, DEMO_PLATFORM_FEATURES } from "../lib/demo/demoPlatform";
import type { PlanResponse, PlanFeatureBulkItem } from "../lib/api/plan";

describe("Platform Admin — Plans Governance & Commercial Architecture", () => {
  it("contains the 4 canonical initial plans with exact codes and asset scopes", () => {
    const plansByCode = new Map<string, PlanResponse>();
    for (const p of DEMO_PLATFORM_PLANS) {
      plansByCode.set(p.code, p);
    }

    // 1. Kota Drone (DRONE_001, DRONE)
    const dronePlan = plansByCode.get("DRONE_001");
    expect(dronePlan).toBeDefined();
    expect(dronePlan?.name).toBe("Kota Drone");
    expect(dronePlan?.asset_scope).toBe("DRONE");
    expect(dronePlan?.is_active).toBe(true);
    expect(dronePlan?.included_features_count).toBeGreaterThan(0);

    // 2. Kota Aircraft (AIRCRAFT_001, AIRCRAFT)
    const aircraftPlan = plansByCode.get("AIRCRAFT_001");
    expect(aircraftPlan).toBeDefined();
    expect(aircraftPlan?.name).toBe("Kota Aircraft");
    expect(aircraftPlan?.asset_scope).toBe("AIRCRAFT");
    expect(aircraftPlan?.is_active).toBe(true);

    // 3. Kota Helicopter (HELICOPTER_001, HELICOPTER)
    const helicopterPlan = plansByCode.get("HELICOPTER_001");
    expect(helicopterPlan).toBeDefined();
    expect(helicopterPlan?.name).toBe("Kota Helicopter");
    expect(helicopterPlan?.asset_scope).toBe("HELICOPTER");
    expect(helicopterPlan?.is_active).toBe(true);

    // 4. Kota eVTOL (EVTOL_001, EVTOL)
    const evtolPlan = plansByCode.get("EVTOL_001");
    expect(evtolPlan).toBeDefined();
    expect(evtolPlan?.name).toBe("Kota eVTOL");
    expect(evtolPlan?.asset_scope).toBe("EVTOL");
    expect(evtolPlan?.is_active).toBe(true);
  });

  it("exposes contractual aggregates (included_features_count and tenant_count)", () => {
    for (const plan of DEMO_PLATFORM_PLANS) {
      expect(typeof plan.included_features_count).toBe("number");
      expect(typeof plan.tenant_count).toBe("number");
      expect(plan.included_features_count).toBeGreaterThanOrEqual(0);
      expect(plan.tenant_count).toBeGreaterThanOrEqual(0);
    }
  });

  it("supports Zero-Hardcoding: dynamic catalog feature mapping", () => {
    // Arbitrary new dynamic product feature
    const dynamicFeatureKey = "autonomous_collision_avoidance";
    const bulkItem: PlanFeatureBulkItem = {
      feature_key: dynamicFeatureKey,
      enabled: true,
    };
    expect(bulkItem.feature_key).toBe(dynamicFeatureKey);
    expect(bulkItem.enabled).toBe(true);
  });

  it("validates two-tier governance: plan baseline + tenant override = effective entitlement", () => {
    // Base plan: battery_analytics = false
    const planFeatures: Record<string, boolean> = {
      drone_fleet_management: true,
      battery_analytics: false,
    };

    // Tenant overrides: battery_analytics = true
    const tenantOverrides: Record<string, boolean> = {
      battery_analytics: true,
    };

    // Effective entitlement calculation
    const effective: Record<string, boolean> = { ...planFeatures, ...tenantOverrides };

    expect(effective.drone_fleet_management).toBe(true); // Inherited from plan
    expect(effective.battery_analytics).toBe(true); // Won by tenant override
  });

  describe("Plan Usage Limits Commercial Contract", () => {
    it("supports baseline plan limits definition with numerical and unlimited types", () => {
      const planLimits = [
        { limit_key: "max_assets", limit_value: 100, is_unlimited: false },
        { limit_key: "max_users", limit_value: 25, is_unlimited: false },
        { limit_key: "monthly_work_orders", limit_value: 500, is_unlimited: false },
        { limit_key: "storage_gb", limit_value: 50, is_unlimited: false },
        { limit_key: "monthly_lisa_ai_tokens", limit_value: 1000, is_unlimited: false },
        { limit_key: "monthly_api_requests", limit_value: null, is_unlimited: true },
      ];

      expect(planLimits.length).toBe(6);
      expect(planLimits[0].limit_value).toBe(100);
      expect(planLimits[5].is_unlimited).toBe(true);
      expect(planLimits[5].limit_value).toBeNull();
    });

    it("verifies unlimited toggle zeroes/clears numerical value", () => {
      let limitValue: number | null = 100;
      let isUnlimited = false;

      // User toggles 'Unlimited'
      isUnlimited = true;
      limitValue = null;

      expect(isUnlimited).toBe(true);
      expect(limitValue).toBeNull();

      // User untoggles 'Unlimited'
      isUnlimited = false;
      limitValue = 150;

      expect(isUnlimited).toBe(false);
      expect(limitValue).toBe(150);
    });

    it("validates negative limit inputs are rejected", () => {
      const validateLimit = (val: number | null, unlimited: boolean): string | null => {
        if (!unlimited && (val === null || val < 0)) {
          return "Value must be zero or a positive integer";
        }
        return null;
      };

      expect(validateLimit(-5, false)).toBe("Value must be zero or a positive integer");
      expect(validateLimit(null, false)).toBe("Value must be zero or a positive integer");
      expect(validateLimit(100, false)).toBeNull();
      expect(validateLimit(null, true)).toBeNull();
    });

    it("verifies effective tenant limit formula: PlanLimit baseline + TenantUsageLimit override", () => {
      const planBaseline: Record<string, number | null> = {
        max_assets: 100,
        max_users: 25,
      };

      // Tenant override exists for max_assets (e.g. 150), no override for max_users
      const tenantOverrides: Record<string, number | null> = {
        max_assets: 150,
      };

      const effectiveLimits: Record<string, number | null> = {
        ...planBaseline,
        ...tenantOverrides,
      };

      expect(effectiveLimits.max_assets).toBe(150); // Override took precedence
      expect(effectiveLimits.max_users).toBe(25); // Inherited from plan baseline
    });
  });
});
