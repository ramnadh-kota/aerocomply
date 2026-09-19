import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { findingsApi } from "../lib/api/findings";
import { ApiError, normalizeApiError } from "../lib/apiClient";

// M20.4: tests for the /findings/[id] detail page's API layer
// (frontend/app/(app)/findings/[id]/page.tsx -> lib/api/findings.ts),
// following this repo's existing convention (see
// tests/platform-invitation.test.ts) of testing the real request/response
// contract a page's handlers call rather than mounting components (no
// React Testing Library is configured in this repo). Covers: successful
// fetch-by-id (what the page renders), 404 normalization (distinct from a
// 5xx), disposition/close actions reused from M20.2/M20.3, and that a
// cross-tenant/nonexistent finding surfaces as "not_found" not a generic
// error -- matching backend/app/services/finding_service.py's NotFoundError.

const ACCESS_TOKEN = "test-access-token";
const FINDING_ID = "33333333-3333-3333-3333-333333333333";

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValueOnce({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

const SAMPLE_FINDING = {
  id: FINDING_ID,
  organization_id: "org-1",
  aircraft_id: "aircraft-1",
  asset_id: null,
  component_id: null,
  inspection_requirement_id: null,
  work_order_id: null,
  task_id: null,
  title: "Hydraulic inspection overdue",
  description: "Detail page test finding",
  severity: "MAJOR",
  status: "OPEN",
  discovered_at: "2026-09-19T00:00:00Z",
  discovered_by_user_id: null,
  responsible_user_id: null,
  created_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
  dispositions: [],
};

describe("findingsApi (M20.4 Finding detail page)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("get() resolves with the persisted Finding for a valid id", async () => {
    global.fetch = mockFetchOnce(200, SAMPLE_FINDING);
    const result = await findingsApi.get(ACCESS_TOKEN, FINDING_ID);
    expect(result.id).toBe(FINDING_ID);
    expect(result.title).toBe("Hydraulic inspection overdue");
    expect(result.status).toBe("OPEN");
  });

  it("get() throws a 404 ApiError for an unknown/cross-tenant id, normalized as not_found", async () => {
    global.fetch = mockFetchOnce(404, { error: { code: "not_found", message: "Finding not found" } });
    await expect(findingsApi.get(ACCESS_TOKEN, "does-not-exist")).rejects.toBeInstanceOf(ApiError);

    global.fetch = mockFetchOnce(404, { error: { code: "not_found", message: "Finding not found" } });
    try {
      await findingsApi.get(ACCESS_TOKEN, "does-not-exist");
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("not_found");
      expect(normalized.message).toBe("Finding not found");
    }
  });

  it("get() throws a 500 ApiError normalized as server, distinct from not_found", async () => {
    global.fetch = mockFetchOnce(500, { error: { code: "internal_error", message: "boom" } });
    try {
      await findingsApi.get(ACCESS_TOKEN, FINDING_ID);
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("server");
      expect(normalized.kind).not.toBe("not_found");
    }
  });

  it("addDisposition() posts the disposition and resolves the updated Finding", async () => {
    const updated = { ...SAMPLE_FINDING, status: "IN_PROGRESS", dispositions: [{ id: "d1", organization_id: "org-1", finding_id: FINDING_ID, disposition_type: "NO_ACTION_REQUIRED", corrective_action: null, evidence_id: null, closed_at: null, closed_by_user_id: null, created_at: "2026-09-19T01:00:00Z" }] };
    global.fetch = mockFetchOnce(200, updated);
    const result = await findingsApi.addDisposition(ACCESS_TOKEN, FINDING_ID, { disposition_type: "NO_ACTION_REQUIRED" });
    expect(result.status).toBe("IN_PROGRESS");
    expect(result.dispositions).toHaveLength(1);
  });

  it("close() posts to the close endpoint and resolves a CLOSED Finding", async () => {
    const closed = { ...SAMPLE_FINDING, status: "CLOSED" };
    global.fetch = mockFetchOnce(200, closed);
    const result = await findingsApi.close(ACCESS_TOKEN, FINDING_ID);
    expect(result.status).toBe("CLOSED");
  });

  it("listForOrganization() supports an optional status filter used by the dashboard's link-through", async () => {
    global.fetch = mockFetchOnce(200, [SAMPLE_FINDING]);
    const result = await findingsApi.listForOrganization(ACCESS_TOKEN, "OPEN");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe(FINDING_ID);
    // findings.slice(0,8).map(f => `/findings/${f.id}`) is what the dashboard
    // links to -- confirm the id shape a real row would produce that href from.
    expect(`/findings/${result[0].id}`).toBe(`/findings/${FINDING_ID}`);
  });
});
