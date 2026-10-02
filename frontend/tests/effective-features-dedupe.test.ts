import { describe, expect, it } from "vitest";
import { dedupeEffectiveFeatures } from "@/lib/entitlements/featureKeys";

describe("dedupeEffectiveFeatures", () => {
  it("collapses the lower-case canonical key and its UPPER-CASE alias into one entry", () => {
    const rows = dedupeEffectiveFeatures({
      drone_fleet_management: true,
      DRONE_FLEET_MANAGEMENT: true,
      lisa_ai_copilot: false,
      LISA_AI_COPILOT: false,
    });
    expect(rows).toHaveLength(2);
    expect(new Map(rows).get("drone_fleet_management")).toBe(true);
    expect(new Map(rows).get("lisa_ai_copilot")).toBe(false);
  });

  it("fails closed when aliases disagree and tolerates empty input", () => {
    expect(new Map(dedupeEffectiveFeatures({ work_order_management: true, WORK_ORDER_MANAGEMENT: false })).get("work_order_management")).toBe(false);
    expect(dedupeEffectiveFeatures(null)).toEqual([]);
  });
});
