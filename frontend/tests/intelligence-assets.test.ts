import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ApiError } from "../lib/apiClient";
import { intelligenceApi, type AssetDecision, type AssetRecommendation } from "../lib/api/intelligence";
import {
  intelligenceReadinessBadge,
  intelligenceRiskLevelBadge,
  intelligenceDecisionBadge,
  intelligenceAerospaceStatusBadge,
} from "../components/status/StatusBadge";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Intelligence API client (M4.1)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  const assetId = "asset-123";

  it("calls the correct readiness endpoint with the bearer token, and never sends organization_id", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        asset_id: assetId,
        aircraft_id: null,
        operational_state: "AVAILABLE",
        readiness_state: "READY",
        blockers: [],
        contributing_factors: {},
        explanation: [],
        data_completeness: "",
        evaluated_at: "2026-01-01T00:00:00Z",
      })
    );

    await intelligenceApi.getReadiness("token-1", assetId);

    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://localhost:8000/api/v1/intelligence/assets/asset-123/readiness");
    expect((options as RequestInit).headers).toMatchObject({ Authorization: "Bearer token-1" });
    // organization_id is derived server-side from the JWT -- never sent by the client.
    const bodyStr = (options as RequestInit).body ? String((options as RequestInit).body) : "";
    expect(bodyStr).not.toContain("organization_id");
  });

  it("calls each of the 5 endpoints with the right path", async () => {
    const paths: string[] = [];
    fetchMock.mockImplementation((url: string) => {
      paths.push(String(url));
      return Promise.resolve(jsonResponse(200, {}));
    });

    await intelligenceApi.getReadiness("t", assetId);
    await intelligenceApi.getRisk("t", assetId);
    await intelligenceApi.getPriority("t", assetId);
    await intelligenceApi.getDecision("t", assetId);
    await intelligenceApi.getRecommendations("t", assetId);

    expect(paths).toEqual([
      "http://localhost:8000/api/v1/intelligence/assets/asset-123/readiness",
      "http://localhost:8000/api/v1/intelligence/assets/asset-123/risk",
      "http://localhost:8000/api/v1/intelligence/assets/asset-123/priority",
      "http://localhost:8000/api/v1/intelligence/assets/asset-123/decision",
      "http://localhost:8000/api/v1/intelligence/assets/asset-123/recommendations",
    ]);
  });

  it("throws a classified ApiError on cross-tenant/nonexistent asset (404)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "not_found", message: "The requested item could not be found." } })
    );

    await expect(intelligenceApi.getReadiness("token-1", "other-org-asset")).rejects.toThrow(ApiError);
  });

  it("throws a classified ApiError on forbidden (403) access", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission to perform this action." } })
    );

    await expect(intelligenceApi.getDecision("token-1", assetId)).rejects.toMatchObject({ status: 403 });
  });

  it("passes through an INSUFFICIENT_DATA decision without collapsing it (empty-state / UNKNOWN handling)", async () => {
    const insufficientDataDecision: AssetDecision = {
      asset_id: assetId,
      aircraft_id: null,
      decision_state: "INSUFFICIENT_DATA",
      decision_reason: "Readiness and/or risk could not be determined.",
      priority_level: "UNKNOWN",
      risk_level: "UNKNOWN",
      readiness_state: "UNKNOWN",
      required_information: ["Readiness intelligence is UNKNOWN."],
      blockers: [],
      warnings: [],
      explanation: [],
      evaluated_at: "2026-01-01T00:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, insufficientDataDecision));

    const result = await intelligenceApi.getDecision("token-1", assetId);

    expect(result.decision_state).toBe("INSUFFICIENT_DATA");
    expect(result.readiness_state).toBe("UNKNOWN");
    expect(result.risk_level).toBe("UNKNOWN");
    expect(result.required_information.length).toBeGreaterThan(0);
  });

  it("preserves full blocker traceability fields on a recommendation item", async () => {
    const recommendation: AssetRecommendation = {
      asset_id: assetId,
      aircraft_id: "aircraft-456",
      recommendation_state: "ACTION_REQUIRED",
      priority_level: "HIGH",
      risk_level: "HIGH",
      readiness_state: "BLOCKED",
      items: [
        {
          action_category: "PERFORM_REQUIRED_ACTION",
          action: "Execute corrective action and attach verified evidence.",
          resolution_condition: "Provide verified evidence satisfying the compliance obligation.",
          source_blocker: {
            source_domain: "AEROSPACE_STATE",
            category: "COMPLIANCE:NON_COMPLIANT_OBLIGATION",
            description: "Regulatory requirement 'Test AD' has been evaluated as NON_COMPLIANT.",
            related_record_id: "obligation-789",
            related_record_type: "ComplianceObligation",
            required_action: "Execute corrective action and attach verified evidence.",
            resolution_action: "Provide verified evidence satisfying the compliance obligation.",
            regulatory_reference: "AD-1: Test AD",
          },
        },
      ],
      required_information: [],
      blockers: [],
      warnings: [],
      explanation: [],
      evaluated_at: "2026-01-01T00:00:00Z",
    };
    fetchMock.mockResolvedValueOnce(jsonResponse(200, recommendation));

    const result = await intelligenceApi.getRecommendations("token-1", assetId);

    expect(result.items[0].source_blocker?.related_record_id).toBe("obligation-789");
    expect(result.items[0].source_blocker?.related_record_type).toBe("ComplianceObligation");
    expect(result.items[0].source_blocker?.regulatory_reference).toBe("AD-1: Test AD");
  });
});

describe("Intelligence badge mappers (M4.4)", () => {
  it("never renders UNKNOWN readiness as READY/COMPLIANT", () => {
    expect(intelligenceReadinessBadge("UNKNOWN").status).toBe("INSUFFICIENT_DATA");
    expect(intelligenceReadinessBadge("UNKNOWN").status).not.toBe("COMPLIANT");
  });

  it("maps READY to the compliant (green) badge and BLOCKED to non-compliant (red)", () => {
    expect(intelligenceReadinessBadge("READY").status).toBe("COMPLIANT");
    expect(intelligenceReadinessBadge("BLOCKED").status).toBe("NON_COMPLIANT");
  });

  it("never renders UNKNOWN risk/priority as LOW", () => {
    expect(intelligenceRiskLevelBadge("UNKNOWN").status).toBe("INSUFFICIENT_DATA");
    expect(intelligenceRiskLevelBadge("UNKNOWN").status).not.toBe("COMPLIANT");
  });

  it("maps CRITICAL risk/priority to the non-compliant (red) badge, not the ambiguous default", () => {
    expect(intelligenceRiskLevelBadge("CRITICAL").status).toBe("NON_COMPLIANT");
  });

  it("never renders INSUFFICIENT_DATA decision as NO_ACTION_REQUIRED", () => {
    const badge = intelligenceDecisionBadge("INSUFFICIENT_DATA");
    expect(badge.status).toBe("INSUFFICIENT_DATA");
    expect(badge.label).toBe("Insufficient Data");
  });

  it("distinguishes ACTION_REQUIRED from IMMEDIATE_ACTION_REQUIRED by label even though both are red", () => {
    const action = intelligenceDecisionBadge("ACTION_REQUIRED");
    const immediate = intelligenceDecisionBadge("IMMEDIATE_ACTION_REQUIRED");
    expect(action.status).toBe("NON_COMPLIANT");
    expect(immediate.status).toBe("NON_COMPLIANT");
    expect(action.label).not.toBe(immediate.label);
  });

  it("never renders UNKNOWN_INTEL aerospace status as NOMINAL", () => {
    expect(intelligenceAerospaceStatusBadge("UNKNOWN_INTEL").status).toBe("INSUFFICIENT_DATA");
    expect(intelligenceAerospaceStatusBadge("UNKNOWN_INTEL").status).not.toBe("COMPLIANT");
  });
});
