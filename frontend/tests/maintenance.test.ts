// M17.4C: Maintenance frontend -- API client requests and status/label
// mapping. Same convention as tests/flight-operations.test.ts and
// tests/drone-lifecycle.test.ts: Node-only vitest, no DOM, so these test
// the pure request-shape and mapping logic feeding the UI.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { dronesApi, canRecordFlight } from "../lib/api/drones";
import { maintenanceDueStatusBadge } from "../components/status/StatusBadge";
import { normalizeApiError, type CurrentUser } from "../lib/apiClient";

function jsonResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

function makeUser(roles: string[]): CurrentUser {
  return {
    id: "user-1",
    organization_id: "org-1",
    email: "u@example.com",
    email_verified: true,
    full_name: "Test User",
    roles,
  };
}

describe("dronesApi maintenance requests (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("requests maintenance-due at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await dronesApi.getMaintenanceDue("token-1", "asset-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/asset-1\/maintenance-due$/);
  });

  it("creates a maintenance requirement with the exact backend request schema", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "req-1" }));
    await dronesApi.createMaintenanceRequirement("token-1", {
      description: "Rotor inspection",
      ata_chapter: "61",
      interval_type: "FLIGHT_HOURS",
      fh_interval: 100,
      fc_interval: null,
      calendar_interval_days: null,
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/maintenance-requirements$/);
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({
      description: "Rotor inspection",
      ata_chapter: "61",
      interval_type: "FLIGHT_HOURS",
      fh_interval: 100,
      fc_interval: null,
      calendar_interval_days: null,
    });
  });

  it("links a requirement to a drone at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "req-1" }));
    await dronesApi.addMaintenanceApplicability("token-1", "asset-1", "req-1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/asset-1\/maintenance-requirements\/req-1\/applicability$/);
    expect(options.method).toBe("POST");
  });

  it("records an accomplishment with the exact backend request schema", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "accm-1" }));
    await dronesApi.recordMaintenanceAccomplishment("token-1", "asset-1", "req-1", {
      accomplished_at: "2026-01-02",
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(
      /\/drones\/asset-1\/maintenance-requirements\/req-1\/accomplishments$/
    );
    const body = JSON.parse(options.body);
    expect(body).toEqual({ accomplished_at: "2026-01-02" });
  });

  it("never sends an organization_id when creating a requirement (SECURITY)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "req-1" }));
    await dronesApi.createMaintenanceRequirement("token-1", {
      description: "x",
      ata_chapter: "05",
      interval_type: "CALENDAR",
      calendar_interval_days: 30,
    });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).not.toMatch(/organization_id/);
  });

  it("propagates a 403 for unauthorized maintenance-due access", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission." } })
    );
    try {
      await dronesApi.getMaintenanceDue("token-1", "asset-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("forbidden");
    }
  });

  it("propagates a 404 for a cross-tenant/missing asset", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "not_found", message: "Drone not found" } })
    );
    try {
      await dronesApi.getMaintenanceDue("token-1", "missing");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("not_found");
    }
  });

  it("a network failure normalizes to the offline kind", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    try {
      await dronesApi.getMaintenanceDue("token-1", "asset-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("offline");
    }
  });
});

describe("maintenanceDueStatusBadge (STATUS UI)", () => {
  it("maps NOT_DUE to the compliant look", () => {
    expect(maintenanceDueStatusBadge("NOT_DUE").status).toBe("COMPLIANT");
  });

  it("maps DUE_SOON to the review-required look", () => {
    expect(maintenanceDueStatusBadge("DUE_SOON").status).toBe("REVIEW_REQUIRED");
  });

  it("maps OVERDUE to the non-compliant look", () => {
    expect(maintenanceDueStatusBadge("OVERDUE").status).toBe("NON_COMPLIANT");
  });

  it("maps UNKNOWN to the insufficient-data look, never fabricating a status", () => {
    expect(maintenanceDueStatusBadge("UNKNOWN").status).toBe("INSUFFICIENT_DATA");
  });

  it("every real backend status has a distinct visual (never color-only ambiguity)", () => {
    const statuses = ["NOT_DUE", "DUE_SOON", "OVERDUE", "UNKNOWN"];
    const mapped = statuses.map((s) => maintenanceDueStatusBadge(s).status);
    expect(new Set(mapped).size).toBe(statuses.length);
  });
});

describe("canRecordFlight reused as the maintenance-write UX gate (PERMISSIONS)", () => {
  it("matches the same DRONE_WRITE role set used for flights", () => {
    expect(canRecordFlight(makeUser(["ORG_ADMIN"]))).toBe(true);
    expect(canRecordFlight(makeUser(["CAMO_MANAGER"]))).toBe(true);
    expect(canRecordFlight(makeUser(["VIEWER"]))).toBe(false);
    expect(canRecordFlight(null)).toBe(false);
  });
});
