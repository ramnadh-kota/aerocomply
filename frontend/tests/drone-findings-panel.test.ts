import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { findingsApi } from "../lib/api/findings";
import { ApiError, normalizeApiError } from "../lib/apiClient";

// M20.6: tests for the drone detail page's Findings panel
// (frontend/app/(app)/drones/[id]/page.tsx -> DroneFindingsPanel ->
// lib/api/findings.ts), following this repo's existing convention (see
// tests/finding-detail.test.ts, tests/platform-invitation.test.ts) of
// testing the real request/response contract a component's handlers call
// rather than mounting components (no React Testing Library is configured
// in this repo). Covers: listForAsset() resolving real findings for a
// drone, empty result handling, 404/error normalization, create() with
// asset_id (instead of aircraft_id, as AircraftFindingsPanel uses), and
// addDisposition()/close() reused verbatim from the aircraft panel.

const ACCESS_TOKEN = "test-access-token";
const DRONE_ID = "44444444-4444-4444-4444-444444444444";
const FINDING_ID = "55555555-5555-5555-5555-555555555555";

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValueOnce({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

const SAMPLE_DRONE_FINDING = {
  id: FINDING_ID,
  organization_id: "org-1",
  aircraft_id: null,
  asset_id: DRONE_ID,
  component_id: null,
  inspection_requirement_id: null,
  work_order_id: null,
  task_id: null,
  title: "Propeller blade nick observed",
  description: "Drone findings panel test finding",
  severity: "MINOR",
  status: "OPEN",
  discovered_at: "2026-09-20T00:00:00Z",
  discovered_by_user_id: null,
  responsible_user_id: null,
  created_at: "2026-09-20T00:00:00Z",
  updated_at: "2026-09-20T00:00:00Z",
  dispositions: [],
};

describe("findingsApi (M20.6 DroneFindingsPanel)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("listForAsset() resolves the findings linked to a drone via asset_id", async () => {
    global.fetch = mockFetchOnce(200, [SAMPLE_DRONE_FINDING]);
    const result = await findingsApi.listForAsset(ACCESS_TOKEN, DRONE_ID);
    expect(result).toHaveLength(1);
    expect(result[0].asset_id).toBe(DRONE_ID);
    expect(result[0].aircraft_id).toBeNull();
  });

  it("listForAsset() calls GET /findings with an asset_id query filter", async () => {
    const fetchMock = mockFetchOnce(200, []);
    global.fetch = fetchMock;
    await findingsApi.listForAsset(ACCESS_TOKEN, DRONE_ID);
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("/findings?asset_id=");
    expect(calledUrl).toContain(DRONE_ID);
  });

  it("listForAsset() resolves an empty array when the drone has no findings yet", async () => {
    global.fetch = mockFetchOnce(200, []);
    const result = await findingsApi.listForAsset(ACCESS_TOKEN, DRONE_ID);
    expect(result).toEqual([]);
  });

  it("listForAsset() throws a 404 ApiError normalized as not_found", async () => {
    global.fetch = mockFetchOnce(404, { error: { code: "not_found", message: "Drone not found" } });
    await expect(findingsApi.listForAsset(ACCESS_TOKEN, "does-not-exist")).rejects.toBeInstanceOf(ApiError);

    global.fetch = mockFetchOnce(404, { error: { code: "not_found", message: "Drone not found" } });
    try {
      await findingsApi.listForAsset(ACCESS_TOKEN, "does-not-exist");
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("not_found");
    }
  });

  it("listForAsset() throws a 500 ApiError normalized as server", async () => {
    global.fetch = mockFetchOnce(500, { error: { code: "internal_error", message: "boom" } });
    try {
      await findingsApi.listForAsset(ACCESS_TOKEN, DRONE_ID);
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("server");
    }
  });

  it("create() raises a finding against a drone via asset_id (not aircraft_id)", async () => {
    const fetchMock = mockFetchOnce(201, SAMPLE_DRONE_FINDING);
    global.fetch = fetchMock;
    const result = await findingsApi.create(ACCESS_TOKEN, {
      title: SAMPLE_DRONE_FINDING.title,
      description: SAMPLE_DRONE_FINDING.description,
      severity: "MINOR",
      asset_id: DRONE_ID,
    });
    expect(result.asset_id).toBe(DRONE_ID);

    const [, init] = fetchMock.mock.calls[0];
    const sentBody = JSON.parse((init as RequestInit).body as string);
    expect(sentBody.asset_id).toBe(DRONE_ID);
    expect(sentBody.aircraft_id).toBeUndefined();
  });

  it("addDisposition() reuses the same endpoint AircraftFindingsPanel uses for a drone-linked finding", async () => {
    const updated = {
      ...SAMPLE_DRONE_FINDING,
      status: "IN_PROGRESS",
      dispositions: [
        {
          id: "d1",
          organization_id: "org-1",
          finding_id: FINDING_ID,
          disposition_type: "NO_ACTION_REQUIRED",
          corrective_action: null,
          evidence_id: null,
          closed_at: null,
          closed_by_user_id: null,
          created_at: "2026-09-20T01:00:00Z",
        },
      ],
    };
    global.fetch = mockFetchOnce(200, updated);
    const result = await findingsApi.addDisposition(ACCESS_TOKEN, FINDING_ID, {
      disposition_type: "NO_ACTION_REQUIRED",
    });
    expect(result.status).toBe("IN_PROGRESS");
    expect(result.dispositions).toHaveLength(1);
  });

  it("close() closes a drone-linked finding after disposition, reused verbatim from the aircraft panel", async () => {
    const closed = { ...SAMPLE_DRONE_FINDING, status: "CLOSED" };
    global.fetch = mockFetchOnce(200, closed);
    const result = await findingsApi.close(ACCESS_TOKEN, FINDING_ID);
    expect(result.status).toBe("CLOSED");
    expect(result.asset_id).toBe(DRONE_ID);
  });
});
