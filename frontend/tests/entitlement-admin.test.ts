import { describe, it, expect } from "vitest";
import {
  getOverrideExpirationState,
  type TenantFeatureOverrideResponse,
} from "../lib/api/entitlement";
import { ApiError, normalizeApiError } from "../lib/apiClient";

describe("Tenant Entitlement & Overrides Administration (M11)", () => {
  const baseTime = new Date("2026-06-01T12:00:00Z");

  describe("getOverrideExpirationState", () => {
    it("identifies permanent override when expires_at is null", () => {
      const override: TenantFeatureOverrideResponse = {
        id: "ov-1",
        organization_id: "org-1",
        feature_key: "maintenance.work_orders",
        enabled: true,
        reason: "VIP override",
        expires_at: null,
        created_at: "2026-01-01T00:00:00Z",
      };

      const result = getOverrideExpirationState(override, baseTime);
      expect(result.state).toBe("PERMANENT");
      expect(result.label).toBe("Permanent (No Expiry)");
      expect(result.isApplicable).toBe(true);
    });

    it("identifies active override when expiration is comfortably in the future", () => {
      const override: TenantFeatureOverrideResponse = {
        id: "ov-2",
        organization_id: "org-1",
        feature_key: "maintenance.work_orders",
        enabled: true,
        reason: "Trial access",
        expires_at: "2026-06-10T12:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      };

      const result = getOverrideExpirationState(override, baseTime);
      expect(result.state).toBe("ACTIVE");
      expect(result.label).toBe("Active");
      expect(result.isApplicable).toBe(true);
    });

    it("identifies expiring soon override when expiration is within 24 hours", () => {
      const override: TenantFeatureOverrideResponse = {
        id: "ov-3",
        organization_id: "org-1",
        feature_key: "maintenance.work_orders",
        enabled: true,
        reason: "Ending trial",
        expires_at: "2026-06-01T18:00:00Z", // 6 hours away
        created_at: "2026-01-01T00:00:00Z",
      };

      const result = getOverrideExpirationState(override, baseTime);
      expect(result.state).toBe("EXPIRING_SOON");
      expect(result.label).toBe("Expires Soon");
      expect(result.isApplicable).toBe(true);
    });

    it("identifies expired override when expiration is in the past", () => {
      const override: TenantFeatureOverrideResponse = {
        id: "ov-4",
        organization_id: "org-1",
        feature_key: "maintenance.work_orders",
        enabled: true,
        reason: "Old promo",
        expires_at: "2026-05-31T00:00:00Z",
        created_at: "2026-01-01T00:00:00Z",
      };

      const result = getOverrideExpirationState(override, baseTime);
      expect(result.state).toBe("EXPIRED");
      expect(result.label).toBe("Expired");
      expect(result.isApplicable).toBe(false);
    });

    it("identifies invalid date strings as expired/not applicable", () => {
      const override: TenantFeatureOverrideResponse = {
        id: "ov-5",
        organization_id: "org-1",
        feature_key: "maintenance.work_orders",
        enabled: true,
        reason: "Bad date",
        expires_at: "not-a-valid-date",
        created_at: "2026-01-01T00:00:00Z",
      };

      const result = getOverrideExpirationState(override, baseTime);
      expect(result.state).toBe("EXPIRED");
      expect(result.label).toBe("Invalid Expiration");
      expect(result.isApplicable).toBe(false);
    });
  });

  describe("API Error Normalization for M11 Entitlement & Limits Scenarios", () => {
    it("handles 403 PLATFORM_ENTITLEMENT_OVERRIDE error message cleanly", () => {
      const apiErr = new ApiError(
        403,
        "permission_denied",
        "Additional permission required: PLATFORM_ENTITLEMENT_OVERRIDE (expansive change)"
      );
      const normalized = normalizeApiError(apiErr);
      expect(normalized.kind).toBe("forbidden");
      expect(normalized.status).toBe(403);
      expect(normalized.message).toContain("PLATFORM_ENTITLEMENT_OVERRIDE");
    });

    it("handles 409 duplicate feature override conflict cleanly", () => {
      const apiErr = new ApiError(
        409,
        "duplicate_feature_override",
        "Feature override already exists for feature 'compliance.audit'"
      );
      const normalized = normalizeApiError(apiErr);
      expect(normalized.kind).toBe("conflict");
      expect(normalized.status).toBe(409);
      expect(normalized.message).toContain("Feature override already exists");
    });

    it("handles 409 duplicate usage limit conflict cleanly", () => {
      const apiErr = new ApiError(
        409,
        "duplicate_usage_limit",
        "Usage limit already exists for feature 'compliance.audit' and limit 'monthly_runs'"
      );
      const normalized = normalizeApiError(apiErr);
      expect(normalized.kind).toBe("conflict");
      expect(normalized.status).toBe(409);
      expect(normalized.message).toContain("Usage limit already exists");
    });

    it("handles 422 unprocessable entity schema error", () => {
      const apiErr = new ApiError(
        422,
        "validation_error",
        "limit_key is required"
      );
      const normalized = normalizeApiError(apiErr);
      expect(normalized.kind).toBe("validation");
      expect(normalized.status).toBe(422);
      expect(normalized.message).toContain("limit_key is required");
    });

    it("handles 404 not found for organization or feature override", () => {
      const apiErr = new ApiError(
        404,
        "not_found",
        "Feature override not found for key 'custom.feature'"
      );
      const normalized = normalizeApiError(apiErr);
      expect(normalized.kind).toBe("not_found");
      expect(normalized.status).toBe(404);
      expect(normalized.message).toContain("Feature override not found");
    });

    it("handles 500 internal server error safely without leaking internals", () => {
      const apiErr = new ApiError(
        500,
        "internal_server_error",
        "Database connection timeout trace..."
      );
      const normalized = normalizeApiError(apiErr);
      expect(normalized.kind).toBe("server");
      expect(normalized.status).toBe(500);
      expect(normalized.message).toBe("The server encountered an error. Please try again later.");
    });
  });
});
