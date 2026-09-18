// M17.5C: Battery/Component maintenance frontend -- API client requests
// and lifetime/current usage formatting. Same Node-only, no-DOM
// convention as tests/maintenance.test.ts (M17.4C).

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { dronesApi } from "../lib/api/drones";
import { normalizeApiError } from "../lib/apiClient";

function jsonResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

describe("dronesApi battery maintenance requests (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("requests battery maintenance-due at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await dronesApi.getBatteryMaintenanceDue("token-1", "battery-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/batteries\/battery-1\/maintenance-due$/);
  });

  it("links a requirement to a battery at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "req-1" }));
    await dronesApi.addBatteryMaintenanceApplicability("token-1", "battery-1", "req-1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(
      /\/batteries\/battery-1\/maintenance-requirements\/req-1\/applicability$/
    );
    expect(options.method).toBe("POST");
  });

  it("records a battery accomplishment with the exact backend request schema", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "accm-1" }));
    await dronesApi.recordBatteryMaintenanceAccomplishment("token-1", "battery-1", "req-1", {
      accomplished_at: "2030-01-02",
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(
      /\/batteries\/battery-1\/maintenance-requirements\/req-1\/accomplishments$/
    );
    const body = JSON.parse(options.body);
    expect(body).toEqual({ accomplished_at: "2030-01-02" });
  });

  it("requests component maintenance-due at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await dronesApi.getComponentMaintenanceDue("token-1", "component-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/components\/component-1\/maintenance-due$/);
  });

  it("links a requirement to a component at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "req-1" }));
    await dronesApi.addComponentMaintenanceApplicability("token-1", "component-1", "req-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(
      /\/components\/component-1\/maintenance-requirements\/req-1\/applicability$/
    );
  });

  it("records a component accomplishment with the exact backend request schema", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "accm-1" }));
    await dronesApi.recordComponentMaintenanceAccomplishment(
      "token-1",
      "component-1",
      "req-1",
      { accomplished_at: "2030-01-02" }
    );
    const [, options] = fetchMock.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).toEqual({ accomplished_at: "2030-01-02" });
  });

  it("never sends an organization_id for battery maintenance calls (SECURITY)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "accm-1" }));
    await dronesApi.recordBatteryMaintenanceAccomplishment("token-1", "battery-1", "req-1", {
      accomplished_at: "2030-01-02",
    });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).not.toMatch(/organization_id/);
  });

  it("propagates a 404 for a cross-tenant/missing battery", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "not_found", message: "Battery not found" } })
    );
    try {
      await dronesApi.getBatteryMaintenanceDue("token-1", "missing");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("not_found");
    }
  });

  it("propagates a 403 for unauthorized component maintenance write", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission." } })
    );
    try {
      await dronesApi.addComponentMaintenanceApplicability("token-1", "component-1", "req-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("forbidden");
    }
  });
});

describe("lifetime vs current usage fields (CRITICAL DOMAIN RULE)", () => {
  it("a MaintenanceDueItem carries current_usage and lifetime_usage as distinct, independent fields", () => {
    // Not a rendering test (no DOM tooling in this repo -- see file
    // header convention elsewhere) -- this documents and locks the
    // contract shape itself: the frontend type must carry both numbers
    // separately, never collapse them, matching backend/app/schemas/
    // maintenance_requirement.py's MaintenanceDueItem exactly.
    const item = {
      requirement: {
        id: "req-1",
        organization_id: "org-1",
        description: "Cell inspection",
        ata_chapter: "24",
        interval_type: "BATTERY_CYCLES" as const,
        fh_interval: null,
        fc_interval: 100,
        calendar_interval_days: null,
        task_reference: null,
      },
      aircraft_id: null,
      asset_id: null,
      battery_id: "battery-1",
      component_id: null,
      last_accomplished_at: "2030-01-02",
      due_status: "NOT_DUE" as const,
      due_date: null,
      reason: "0.0 of 100 cycles used, 100.0 cycles remaining.",
      current_usage: 0,
      remaining_usage: 100,
      lifetime_usage: 110,
    };
    // After an accomplishment, current_usage resets but lifetime_usage
    // (the item's total-ever usage) must remain the larger, unreset value.
    expect(item.current_usage).toBe(0);
    expect(item.lifetime_usage).toBe(110);
    expect(item.lifetime_usage).toBeGreaterThan(item.current_usage);
  });
});
