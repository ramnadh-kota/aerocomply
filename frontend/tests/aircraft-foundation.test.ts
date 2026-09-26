// Slice B: Aircraft foundation fixes -- canonical POST /aircraft creation
// path (now reachable from the "Add Aircraft" UI instead of only the
// generic /assets path), PATCH /aircraft/{id} editing, and that the
// existing Demo Add-Aircraft flow (demoStore, never touching the real
// backend) is untouched. Same convention as tests/flight-operations.test.ts:
// this project's vitest environment is Node-only (no jsdom/@testing-library),
// so these test the exact request/response shapes and demo-isolation logic
// feeding the UI, not a DOM render.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { aircraftApi } from "../lib/api/aircraft";
import { ApiError, normalizeApiError } from "../lib/apiClient";
import { demoStore } from "../lib/demo/demoStore";
import { DEMO_ORG_ID } from "../lib/auth/SessionContext";

function jsonResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

describe("aircraftApi.create (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("POSTs to /aircraft with the exact backend request schema", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, {
        id: "aircraft-1",
        organization_id: "org-1",
        registration: "N100AC",
        msn: "MSN-100",
        aircraft_type: "A320",
        status: "ACTIVE",
        created_at: "2026-01-01T00:00:00Z",
      })
    );
    await aircraftApi.create("token-1", {
      registration: "N100AC",
      msn: "MSN-100",
      aircraft_type: "A320",
      status: "ACTIVE",
      manufacturer: "Airbus",
    });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/aircraft$/);
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({
      registration: "N100AC",
      msn: "MSN-100",
      aircraft_type: "A320",
      status: "ACTIVE",
      manufacturer: "Airbus",
    });
  });

  it("never sends an organization_id when creating an aircraft (SECURITY)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(201, { id: "aircraft-1" }));
    await aircraftApi.create("token-1", {
      registration: "N101AC",
      msn: "MSN-101",
      aircraft_type: "A320",
    });
    const [, options] = fetchMock.mock.calls[0];
    expect(options.body).not.toMatch(/organization_id/);
  });

  it("propagates a 409 duplicate-registration conflict", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, { error: { code: "duplicate_registration", message: "Aircraft registration already exists" } })
    );
    try {
      await aircraftApi.create("token-1", { registration: "N102AC", msn: "MSN-102", aircraft_type: "A320" });
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect(normalizeApiError(err).kind).toBe("conflict");
    }
  });
});

describe("aircraftApi.update (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("PATCHes /aircraft/{id} with only the changed fields", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        id: "aircraft-1",
        organization_id: "org-1",
        registration: "N100AC",
        msn: "MSN-100-REV2",
        aircraft_type: "A320",
        status: "MAINTENANCE",
        created_at: "2026-01-01T00:00:00Z",
      })
    );
    await aircraftApi.update("token-1", "aircraft-1", { msn: "MSN-100-REV2", status: "MAINTENANCE" });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/aircraft\/aircraft-1$/);
    expect(options.method).toBe("PATCH");
    const body = JSON.parse(options.body);
    expect(body).toEqual({ msn: "MSN-100-REV2", status: "MAINTENANCE" });
  });

  it("propagates a 404 for a cross-tenant / missing aircraft", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "not_found", message: "Aircraft not found" } })
    );
    try {
      await aircraftApi.update("token-1", "missing", { status: "GROUNDED" });
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("not_found");
    }
  });

  it("a network failure normalizes to the offline kind", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    try {
      await aircraftApi.update("token-1", "aircraft-1", { status: "GROUNDED" });
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("offline");
    }
  });
});

describe("Demo Add-Aircraft flow is untouched (DEMO ISOLATION)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    demoStore.reset();
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("adding a demo AIRCRAFT asset never calls the real backend", () => {
    const created = demoStore.addAsset({
      asset_type: "AIRCRAFT",
      registration: "N-DEMO-AC1",
      manufacturer: "Boeing",
      model: "737-800",
    });
    expect(created.asset_type).toBe("AIRCRAFT");
    expect(created.organization_id).toBe(DEMO_ORG_ID);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(demoStore.getAssetById(created.id)?.registration).toBe("N-DEMO-AC1");
  });
});
