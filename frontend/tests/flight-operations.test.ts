// M17.3C: Flight Operations frontend -- API client requests, permission
// UX-hint mapping, and history/pagination shaping logic. Same convention
// as tests/drone-lifecycle.test.ts (M17.2C): this project's vitest
// environment is Node-only, no jsdom/@testing-library/react anywhere in
// the repo, so these test the exact pure logic feeding the UI (request
// shape, pagination math, permission mapping) rather than a DOM render.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { dronesApi, canRecordFlight } from "../lib/api/drones";
import { ApiError, normalizeApiError, type CurrentUser } from "../lib/apiClient";

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

describe("dronesApi flight requests (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("requests flight history at the exact backend path with pagination params", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 10, offset: 0 }));
    await dronesApi.listFlights("token-1", "asset-1", { limit: 10, offset: 20 });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/asset-1\/flights\?limit=10&offset=20$/);
  });

  it("requests flight history with no params when none given", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await dronesApi.listFlights("token-1", "asset-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/asset-1\/flights$/);
  });

  it("requests flight detail at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "flight-1" }));
    await dronesApi.getFlight("token-1", "flight-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/flights\/flight-1$/);
  });

  it("requests utilization at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, { asset_id: "asset-1", total_flights: 0, total_minutes: 0, total_cycles: 0 })
    );
    await dronesApi.getUtilization("token-1", "asset-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/asset-1\/utilization$/);
  });

  it("sends the exact backend request schema when recording a flight", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "flight-1" }));
    await dronesApi.recordFlight("token-1", "asset-1", {
      flown_at: "2026-01-01T00:00:00Z",
      duration_minutes: 30,
      cycles: 2,
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/asset-1\/flights$/);
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({ flown_at: "2026-01-01T00:00:00Z", duration_minutes: 30, cycles: 2 });
  });

  it("never sends an organization_id when recording a flight (SECURITY)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "flight-1" }));
    await dronesApi.recordFlight("token-1", "asset-1", {
      flown_at: "2026-01-01T00:00:00Z",
      duration_minutes: 10,
      cycles: 1,
    });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).not.toMatch(/organization_id/);
  });

  it("propagates a 422 validation error", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(422, { error: { code: "validation_error", message: "duration_minutes must be positive" } })
    );
    try {
      await dronesApi.recordFlight("token-1", "asset-1", {
        flown_at: "2026-01-01T00:00:00Z",
        duration_minutes: -5,
        cycles: 1,
      });
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("validation");
    }
  });

  it("propagates a 404 for a missing flight", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "not_found", message: "Flight not found" } })
    );
    try {
      await dronesApi.getFlight("token-1", "missing");
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect(normalizeApiError(err).kind).toBe("not_found");
    }
  });

  it("propagates a 403 for unauthorized flight history access", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission." } })
    );
    try {
      await dronesApi.listFlights("token-1", "asset-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("forbidden");
    }
  });

  it("a network failure normalizes to the offline kind", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    try {
      await dronesApi.listFlights("token-1", "asset-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("offline");
    }
  });
});

describe("canRecordFlight (PERMISSIONS)", () => {
  it("returns false for no user", () => {
    expect(canRecordFlight(null)).toBe(false);
  });

  it("returns true for roles with DRONE_WRITE", () => {
    expect(canRecordFlight(makeUser(["ORG_ADMIN"]))).toBe(true);
    expect(canRecordFlight(makeUser(["CAMO_MANAGER"]))).toBe(true);
    expect(canRecordFlight(makeUser(["SUPER_ADMIN"]))).toBe(true);
  });

  it("returns false for DRONE_READ-only roles", () => {
    expect(canRecordFlight(makeUser(["VIEWER"]))).toBe(false);
    expect(canRecordFlight(makeUser(["COMPLIANCE_MANAGER"]))).toBe(false);
    expect(canRecordFlight(makeUser(["QUALITY_MANAGER"]))).toBe(false);
    expect(canRecordFlight(makeUser(["MAINTENANCE_ENGINEER"]))).toBe(false);
  });

  it("returns false for a role with no drone permission at all", () => {
    expect(canRecordFlight(makeUser(["PLATFORM_STAFF"]))).toBe(false);
  });
});

describe("flight-history pagination math (FLIGHT HISTORY)", () => {
  // Mirrors the from/to/hasPrevious/hasNext logic in
  // components/flights/FlightHistoryTable.tsx -- kept here as a plain
  // function so the arithmetic itself is directly testable without a DOM.
  function paginationState(total: number, limit: number, offset: number) {
    const from = total === 0 ? 0 : offset + 1;
    const to = Math.min(offset + limit, total);
    return { from, to, hasPrevious: offset > 0, hasNext: offset + limit < total };
  }

  it("first page of a multi-page result", () => {
    const state = paginationState(25, 10, 0);
    expect(state).toEqual({ from: 1, to: 10, hasPrevious: false, hasNext: true });
  });

  it("middle page of a multi-page result", () => {
    const state = paginationState(25, 10, 10);
    expect(state).toEqual({ from: 11, to: 20, hasPrevious: true, hasNext: true });
  });

  it("last page of a multi-page result", () => {
    const state = paginationState(25, 10, 20);
    expect(state).toEqual({ from: 21, to: 25, hasPrevious: true, hasNext: false });
  });

  it("empty history", () => {
    const state = paginationState(0, 10, 0);
    expect(state).toEqual({ from: 0, to: 0, hasPrevious: false, hasNext: false });
  });

  it("single page exactly fitting the limit", () => {
    const state = paginationState(10, 10, 0);
    expect(state).toEqual({ from: 1, to: 10, hasPrevious: false, hasNext: false });
  });
});
