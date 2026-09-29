import { describe, it, expect, vi, beforeEach } from "vitest";
import { normalizeFeatureKey, hasFeatureKey } from "../lib/entitlements/featureKeys";

describe("Frontend Canonical Feature Keys & Normalization", () => {
  it("normalizes uppercase and legacy aliases to canonical feature key", () => {
    expect(normalizeFeatureKey("DIGITAL_TWIN")).toBe("digital_twin");
    expect(normalizeFeatureKey("DIGITAL_TWIN_BETA")).toBe("digital_twin");
    expect(normalizeFeatureKey("digital_twin_beta")).toBe("digital_twin");
    expect(normalizeFeatureKey("HUMS")).toBe("hums");
    expect(normalizeFeatureKey("hums_module")).toBe("hums");
    expect(normalizeFeatureKey("LISA")).toBe("lisa_ai_copilot");
    expect(normalizeFeatureKey("LISA_AI_COPILOT")).toBe("lisa_ai_copilot");
    expect(normalizeFeatureKey("MRO_INTELLIGENCE")).toBe("mro_intelligence");
    expect(normalizeFeatureKey("mro_intelligence_module")).toBe("mro_intelligence");
  });

  it("checks hasFeatureKey across aliases correctly", () => {
    const entitlements = {
      digital_twin: true,
      hums: true,
      lisa_ai_copilot: false,
    };

    // Enabled features
    expect(hasFeatureKey(entitlements, "digital_twin")).toBe(true);
    expect(hasFeatureKey(entitlements, "DIGITAL_TWIN")).toBe(true);
    expect(hasFeatureKey(entitlements, "DIGITAL_TWIN_BETA")).toBe(true);
    expect(hasFeatureKey(entitlements, "HUMS")).toBe(true);
    expect(hasFeatureKey(entitlements, "hums_module")).toBe(true);

    // Disabled features
    expect(hasFeatureKey(entitlements, "lisa_ai_copilot")).toBe(false);
    expect(hasFeatureKey(entitlements, "LISA")).toBe(false);

    // Unspecified features default to false when entitlements object is provided
    expect(hasFeatureKey(entitlements, "drone_fleet_management")).toBe(false);

    // Fail open when entitlements is null (e.g. uninitialized or demo mode)
    expect(hasFeatureKey(null, "digital_twin")).toBe(true);
    expect(hasFeatureKey(undefined, "digital_twin")).toBe(true);
  });
});
