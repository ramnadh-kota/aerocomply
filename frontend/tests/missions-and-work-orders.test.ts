// M1.5: Missions, Drone Compliance, and Work Orders filter tests

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { missionsApi } from "../lib/api/missions";
import { complianceAssessmentsApi } from "../lib/api/compliance";
import { workOrdersApi } from "../lib/api/workOrders";
import { getDemoMissionsForDrone, getDemoComplianceForDrone } from "../lib/demo/demoDrones";
import { workOrders } from "../lib/mock/workOrders";

function jsonResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

describe("missionsApi (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("lists missions with query parameters", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await missionsApi.listMissions("token-1", { asset_id: "asset-123", status: "PLANNED" });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/missions?");
    expect(String(url)).toContain("asset_id=asset-123");
    expect(String(url)).toContain("status=PLANNED");
    expect(options.headers.Authorization).toBe("Bearer token-1");
  });

  it("creates a mission", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "m-1", purpose: "Test mission" }));
    await missionsApi.createMission("token-1", {
      asset_id: "asset-123",
      purpose: "Survey Flight",
      operating_area: "Zone A",
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/missions$/);
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.asset_id).toBe("asset-123");
    expect(body.purpose).toBe("Survey Flight");
  });

  it("authorizes a mission internally", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "m-1", status: "AUTHORIZED" }));
    await missionsApi.authorizeMission("token-1", "m-1", { notes: "Lead approval" });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/missions\/m-1\/authorize$/);
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body.notes).toBe("Lead approval");
  });
});

describe("complianceAssessmentsApi for assets (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("lists assessments for an asset", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await complianceAssessmentsApi.listForAsset("token-1", "drone-asset-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/assets\/drone-asset-1\/compliance-assessments$/);
  });

  it("fetches compliance analytics for an asset", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { COMPLIANT: 5 }));
    await complianceAssessmentsApi.analyticsForAsset("token-1", "drone-asset-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/assets\/drone-asset-1\/compliance-analytics$/);
  });
});

describe("workOrdersApi filtering (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("passes asset_id parameter to work-orders list endpoint", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, []));
    await workOrdersApi.list("token-1", { asset_id: "drone-123" });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/work-orders\?asset_id=drone-123$/);
  });
});

describe("DEMO data isolation", () => {
  it("resolves synthetic missions for demo drone without network calls", () => {
    const missions = getDemoMissionsForDrone("drn-kota-001");
    expect(Array.isArray(missions)).toBe(true);
    expect(missions.length).toBeGreaterThan(0);
    expect(missions[0].asset_id).toBe("drn-kota-001");
  });

  it("resolves synthetic compliance determinations for demo drone without network calls", () => {
    const compliance = getDemoComplianceForDrone("drn-kota-001");
    expect(Array.isArray(compliance)).toBe(true);
    expect(compliance.length).toBeGreaterThan(0);
    expect(compliance[0].asset_id).toBe("drn-kota-001");
  });

  it("filters synthetic work orders by asset_id without network calls", () => {
    const d1WorkOrders = workOrders.filter((w) => w.assetId === "drn-kota-001");
    expect(d1WorkOrders.length).toBeGreaterThan(0);
    expect(d1WorkOrders[0].workOrderNumber).toBe("WO-DRN-1001");
  });
});
