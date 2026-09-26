// Platform Control Plane soft-delete governance -- frontend API client for
// GET/POST /platform/deleted-records/... (backend/app/api/v1/platform.py)
// and DELETE /assets/{id} (backend/app/services/deletion_service.py). Same
// convention as tests/flight-operations.test.ts: Node-only vitest, no
// jsdom/@testing-library -- these test exact request shapes and error
// propagation, not a DOM render.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { deletionApi } from "../lib/api/deletion";
import { assetsApi } from "../lib/api/assets";
import { tenantApi } from "../lib/api/tenant";
import { ApiError, normalizeApiError } from "../lib/apiClient";

function jsonResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

describe("assetsApi.deleteAsset (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("DELETEs /assets/{id} with no reason by default", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "asset-1" }));
    await assetsApi.deleteAsset("token-1", "asset-1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/assets\/asset-1$/);
    expect(options.method).toBe("DELETE");
  });

  it("DELETEs /assets/{id} with an encoded reason query param", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "asset-1" }));
    await assetsApi.deleteAsset("token-1", "asset-1", "no longer operational");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("reason=no%20longer%20operational");
  });

  it("propagates a 409 already-deleted conflict", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, { error: { code: "already_deleted", message: "Asset is already deleted" } })
    );
    try {
      await assetsApi.deleteAsset("token-1", "asset-1");
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect(normalizeApiError(err).kind).toBe("conflict");
    }
  });
});

describe("deletionApi (PLATFORM CONTROL PLANE)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("lists deleted records with organization/pagination query params", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await deletionApi.listDeletedRecords("token-1", { organization_id: "org-1", limit: 20, offset: 40 });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records\?organization_id=org-1&limit=20&offset=40$/);
  });

  it("lists deleted records with no query params when none given", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await deletionApi.listDeletedRecords("token-1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records$/);
  });

  it("restores an asset via POST", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "asset-1" }));
    await deletionApi.restoreAsset("token-1", "asset-1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records\/assets\/asset-1\/restore$/);
    expect(options.method).toBe("POST");
  });

  it("permanently deletes an asset with reason and confirm:true", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { message: "Asset permanently deleted." }));
    await deletionApi.permanentlyDeleteAsset("token-1", "asset-1", "cleanup after verification");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records\/assets\/asset-1\/permanent-delete$/);
    const body = JSON.parse(options.body);
    expect(body).toEqual({ reason: "cleanup after verification", confirm: true });
  });

  it("propagates a 403 for a non-platform-admin caller", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission." } })
    );
    try {
      await deletionApi.listDeletedRecords("token-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("forbidden");
    }
  });

  it("propagates a 409 when permanent-delete is blocked by dependent records", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, { error: { code: "has_dependent_records", message: "This asset has dependent records..." } })
    );
    try {
      await deletionApi.permanentlyDeleteAsset("token-1", "asset-1", "attempt purge");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("conflict");
    }
  });

  it("lists deleted records filtered by entity_type=ORGANIZATION", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await deletionApi.listDeletedRecords("token-1", { entity_type: "ORGANIZATION" });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records\?entity_type=ORGANIZATION$/);
  });

  it("restores an organization via POST", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { message: "Organization restored." }));
    await deletionApi.restoreOrganization("token-1", "org-1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records\/organizations\/org-1\/restore$/);
    expect(options.method).toBe("POST");
  });

  it("permanently deletes an organization with reason and confirm:true", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { message: "Organization permanently deleted." }));
    await deletionApi.permanentlyDeleteOrganization("token-1", "org-1", "offboarding complete");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/platform\/deleted-records\/organizations\/org-1\/permanent-delete$/);
    const body = JSON.parse(options.body);
    expect(body).toEqual({ reason: "offboarding complete", confirm: true });
  });
});

describe("tenantApi.requestDeletion (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("POSTs to /tenant/deletion-request with an optional reason", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { message: "Deletion requested." }));
    await tenantApi.requestDeletion("token-1", "closing account");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/tenant\/deletion-request$/);
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual({ reason: "closing account" });
  });

  it("propagates a 403 for a user without ORG_MANAGE", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission." } })
    );
    try {
      await tenantApi.requestDeletion("token-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("forbidden");
    }
  });

  it("propagates a 401 when the token is already refused (org already deletion-requested)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(401, { error: { code: "unauthorized", message: "This organization has requested deletion and is pending review" } })
    );
    try {
      await tenantApi.requestDeletion("token-1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("unauthorized");
    }
  });
});
