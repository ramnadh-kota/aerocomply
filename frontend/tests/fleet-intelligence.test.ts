import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError } from "../lib/apiClient";
import { intelligenceApi, type FleetIntelligenceSummary, type FleetAssetIntelligence } from "../lib/api/intelligence";
import { isUncertain, distinctValues } from "../app/(app)/intelligence/fleet/page";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeAsset(overrides: Partial<FleetAssetIntelligence> = {}): FleetAssetIntelligence {
  return {
    asset_id: "asset-1",
    registration: "N100AB",
    asset_type: "AIRCRAFT",
    operational_state: "AVAILABLE",
    aerospace_intelligence_status: "NOMINAL",
    readiness_state: "READY",
    risk_level: "LOW",
    priority_level: "LOW",
    decision_state: "NO_ACTION_REQUIRED",
    decision_reason: "No blockers or warnings are present.",
    top_recommendation_action: null,
    blocker_count: 0,
    warning_count: 0,
    blockers: [],
    warnings: [],
    evaluated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("Fleet Intelligence API client (M4.2)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("calls GET /intelligence/fleet with the bearer token, never sending organization_id", async () => {
    const summary: FleetIntelligenceSummary = {
      total_assets: 1,
      assets: [makeAsset()],
      evaluated_at: "2026-01-01T00:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, summary));

    const result = await intelligenceApi.getFleet("token-1");

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://localhost:8000/api/v1/intelligence/fleet");
    expect((options as RequestInit).headers).toMatchObject({ Authorization: "Bearer token-1" });
    const bodyStr = (options as RequestInit).body ? String((options as RequestInit).body) : "";
    expect(bodyStr).not.toContain("organization_id");
    // Every value passed through unchanged -- nothing fabricated client-side.
    expect(result).toEqual(summary);
  });

  it("returns real data unmodified (successful fleet load) with real asset count", async () => {
    const summary: FleetIntelligenceSummary = {
      total_assets: 2,
      assets: [makeAsset({ asset_id: "a" }), makeAsset({ asset_id: "b", registration: "N200CD" })],
      evaluated_at: "2026-01-01T00:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, summary));

    const result = await intelligenceApi.getFleet("token-1");

    expect(result.total_assets).toBe(2);
    expect(result.assets).toHaveLength(2);
    expect(result.assets.map((a) => a.registration)).toEqual(["N100AB", "N200CD"]);
  });

  it("handles an empty fleet honestly (empty state, no fabricated rows)", async () => {
    const summary: FleetIntelligenceSummary = { total_assets: 0, assets: [], evaluated_at: "2026-01-01T00:00:00Z" };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, summary));

    const result = await intelligenceApi.getFleet("token-1");

    expect(result.total_assets).toBe(0);
    expect(result.assets).toEqual([]);
  });

  it("throws a classified ApiError on server failure (error state)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(500, { error: { code: "server_error", message: "Internal error" } })
    );

    await expect(intelligenceApi.getFleet("token-1")).rejects.toThrow(ApiError);
  });

  it("throws a classified ApiError on forbidden access (tenant/auth behavior)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission to perform this action." } })
    );

    await expect(intelligenceApi.getFleet("token-1")).rejects.toMatchObject({ status: 403 });
  });

  it("preserves full blocker traceability fields on a fleet asset", async () => {
    const asset = makeAsset({
      blockers: [
        {
          source_domain: "AEROSPACE_STATE",
          category: "COMPLIANCE:NON_COMPLIANT_OBLIGATION",
          description: "Regulatory requirement is NON_COMPLIANT.",
          related_record_id: "obligation-1",
          related_record_type: "ComplianceObligation",
          required_action: "Execute corrective action.",
          resolution_action: "Provide verified evidence.",
          regulatory_reference: "AD-1: Test AD",
        },
      ],
      blocker_count: 1,
    });
    const summary: FleetIntelligenceSummary = { total_assets: 1, assets: [asset], evaluated_at: "2026-01-01T00:00:00Z" };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, summary));

    const result = await intelligenceApi.getFleet("token-1");

    expect(result.assets[0].blockers[0].related_record_id).toBe("obligation-1");
    expect(result.assets[0].blockers[0].required_action).toBe("Execute corrective action.");
    expect(result.assets[0].blockers[0].resolution_action).toBe("Provide verified evidence.");
  });

  it("preserves warning fields on a fleet asset", async () => {
    const asset = makeAsset({
      warnings: [
        {
          warning_id: "w-1",
          category: "REVIEW_REQUIRED_OBLIGATION",
          dimension: "COMPLIANCE",
          message: "Compliance obligation requires manual review.",
          source_type: "ComplianceObligation",
          source_id: "obligation-2",
          source_label: "AD-2",
        },
      ],
      warning_count: 1,
    });
    const summary: FleetIntelligenceSummary = { total_assets: 1, assets: [asset], evaluated_at: "2026-01-01T00:00:00Z" };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, summary));

    const result = await intelligenceApi.getFleet("token-1");

    expect(result.assets[0].warnings[0].message).toBe("Compliance obligation requires manual review.");
  });
});

describe("Fleet Intelligence uncertainty/filter helpers (M4.2)", () => {
  it("flags UNKNOWN_INTEL as uncertain, never as nominal", () => {
    const asset = makeAsset({ aerospace_intelligence_status: "UNKNOWN_INTEL" });
    expect(isUncertain(asset)).toBe(true);
  });

  it("flags UNKNOWN readiness as uncertain", () => {
    const asset = makeAsset({ readiness_state: "UNKNOWN" });
    expect(isUncertain(asset)).toBe(true);
  });

  it("flags UNKNOWN risk as uncertain", () => {
    const asset = makeAsset({ risk_level: "UNKNOWN" });
    expect(isUncertain(asset)).toBe(true);
  });

  it("flags INSUFFICIENT_DATA decision as uncertain, distinct from NO_ACTION_REQUIRED", () => {
    const uncertain = makeAsset({ decision_state: "INSUFFICIENT_DATA" });
    const nominal = makeAsset({ decision_state: "NO_ACTION_REQUIRED" });
    expect(isUncertain(uncertain)).toBe(true);
    expect(isUncertain(nominal)).toBe(false);
  });

  it("a fully nominal asset is never flagged uncertain", () => {
    expect(isUncertain(makeAsset())).toBe(false);
  });

  it("distinctValues extracts only real, present values (no fabricated options)", () => {
    const assets = [
      makeAsset({ asset_type: "AIRCRAFT" }),
      makeAsset({ asset_type: "DRONE" }),
      makeAsset({ asset_type: "AIRCRAFT" }),
    ];
    expect(distinctValues(assets, "asset_type")).toEqual(["AIRCRAFT", "DRONE"]);
  });

  it("distinctValues returns an empty list for an empty fleet", () => {
    expect(distinctValues([], "asset_type")).toEqual([]);
  });
});
