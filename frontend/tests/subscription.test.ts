import { describe, it, expect } from "vitest";
import {
  ALLOWED_TRANSITIONS,
  CREATABLE_STATUSES,
  CURRENT_GRANTING_STATUSES,
  groupSubscription,
  type SubscriptionStatus,
} from "../lib/api/subscription";
import { ApiError, normalizeApiError } from "../lib/apiClient";

describe("Subscription Administration Helpers & Lifecycle Matrix", () => {
  it("defines exact allowed transitions conforming to M6 backend rules", () => {
    expect(ALLOWED_TRANSITIONS["TRIALING"]).toEqual(["ACTIVE", "PAST_DUE", "CANCELED"]);
    expect(ALLOWED_TRANSITIONS["ACTIVE"]).toEqual(["PAST_DUE", "CANCELED"]);
    expect(ALLOWED_TRANSITIONS["PAST_DUE"]).toEqual(["ACTIVE", "CANCELED"]);
    expect(ALLOWED_TRANSITIONS["SCHEDULED"]).toEqual(["TRIALING", "ACTIVE", "CANCELED"]);
    // CANCELED is terminal
    expect(ALLOWED_TRANSITIONS["CANCELED"]).toEqual([]);
  });

  it("defines creatable statuses", () => {
    expect(CREATABLE_STATUSES).toEqual(["TRIALING", "ACTIVE", "PAST_DUE", "SCHEDULED"]);
    expect(CREATABLE_STATUSES).not.toContain("CANCELED");
  });

  it("defines current granting statuses according to M2 candidacy rule", () => {
    expect(CURRENT_GRANTING_STATUSES.has("TRIALING")).toBe(true);
    expect(CURRENT_GRANTING_STATUSES.has("ACTIVE")).toBe(true);
    expect(CURRENT_GRANTING_STATUSES.has("PAST_DUE")).toBe(true);
    expect(CURRENT_GRANTING_STATUSES.has("SCHEDULED")).toBe(false);
    expect(CURRENT_GRANTING_STATUSES.has("CANCELED")).toBe(false);
  });

  describe("groupSubscription", () => {
    const now = new Date("2026-06-01T12:00:00Z");

    it("groups active current subscription as Current", () => {
      const sub = {
        status: "ACTIVE" as SubscriptionStatus,
        starts_at: "2026-01-01T00:00:00Z",
        ends_at: "2026-12-31T23:59:59Z",
      };
      expect(groupSubscription(sub, now)).toBe("Current");
    });

    it("groups open-ended active subscription as Current", () => {
      const sub = {
        status: "ACTIVE" as SubscriptionStatus,
        starts_at: "2026-01-01T00:00:00Z",
        ends_at: null,
      };
      expect(groupSubscription(sub, now)).toBe("Current");
    });

    it("groups past due current subscription as Current", () => {
      const sub = {
        status: "PAST_DUE" as SubscriptionStatus,
        starts_at: "2026-01-01T00:00:00Z",
        ends_at: null,
      };
      expect(groupSubscription(sub, now)).toBe("Current");
    });

    it("groups trialing current subscription as Current", () => {
      const sub = {
        status: "TRIALING" as SubscriptionStatus,
        starts_at: "2026-05-01T00:00:00Z",
        ends_at: "2026-06-15T00:00:00Z",
      };
      expect(groupSubscription(sub, now)).toBe("Current");
    });

    it("groups future-dated active subscription as Upcoming", () => {
      const sub = {
        status: "ACTIVE" as SubscriptionStatus,
        starts_at: "2026-07-01T00:00:00Z",
        ends_at: "2026-12-31T00:00:00Z",
      };
      expect(groupSubscription(sub, now)).toBe("Upcoming");
    });

    it("groups SCHEDULED subscription as Upcoming regardless of start date", () => {
      const sub = {
        status: "SCHEDULED" as SubscriptionStatus,
        starts_at: "2026-01-01T00:00:00Z",
        ends_at: null,
      };
      expect(groupSubscription(sub, now)).toBe("Upcoming");
    });

    it("groups ended subscription as Historical", () => {
      const sub = {
        status: "ACTIVE" as SubscriptionStatus,
        starts_at: "2025-01-01T00:00:00Z",
        ends_at: "2025-12-31T23:59:59Z",
      };
      expect(groupSubscription(sub, now)).toBe("Historical");
    });

    it("groups CANCELED subscription as Historical", () => {
      const sub = {
        status: "CANCELED" as SubscriptionStatus,
        starts_at: "2026-01-01T00:00:00Z",
        ends_at: null,
      };
      expect(groupSubscription(sub, now)).toBe("Historical");
    });
  });

  describe("normalizeApiError for subscription error cases", () => {
    it("handles 401 unauthorized", () => {
      const err = new ApiError(401, "unauthorized", "Not authenticated");
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("unauthorized");
      expect(norm.status).toBe(401);
    });

    it("handles 403 forbidden", () => {
      const err = new ApiError(403, "permission_denied", "Requires PLATFORM_MANAGE");
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("forbidden");
      expect(norm.status).toBe(403);
    });

    it("handles 404 not found", () => {
      const err = new ApiError(404, "not_found", "Organization not found");
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("not_found");
      expect(norm.status).toBe(404);
      expect(norm.message).toBe("Organization not found");
    });

    it("handles 409 conflict (ambiguous_subscription_state)", () => {
      const err = new ApiError(
        409,
        "ambiguous_subscription_state",
        "Creating/updating this subscription would produce two simultaneously-current subscriptions for organization"
      );
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("conflict");
      expect(norm.status).toBe(409);
      expect(norm.message).toContain("simultaneously-current");
    });

    it("handles 409 conflict (invalid_transition)", () => {
      const err = new ApiError(
        409,
        "invalid_transition",
        "Invalid subscription lifecycle transition 'CANCELED' -> 'ACTIVE'"
      );
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("conflict");
      expect(norm.status).toBe(409);
      expect(norm.message).toContain("Invalid subscription lifecycle transition");
    });

    it("handles 422 validation error", () => {
      const err = new ApiError(422, "validation_error", "plan_id is required");
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("validation");
      expect(norm.status).toBe(422);
      expect(norm.message).toBe("plan_id is required");
    });

    it("handles 500 server error safely", () => {
      const err = new ApiError(500, "internal_error", "Internal stack trace details");
      const norm = normalizeApiError(err);
      expect(norm.kind).toBe("server");
      expect(norm.status).toBe(500);
      expect(norm.message).toBe("The server encountered an error. Please try again later.");
    });
  });
});
