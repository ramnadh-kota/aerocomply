import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { platformApi } from "../lib/api/platform";
import { ApiError, normalizeApiError } from "../lib/apiClient";

// M19.2: tests for the "Invite Org Admin" panel's API layer
// (frontend/app/(app)/platform/organizations/[organizationId]/page.tsx ->
// lib/api/platform.ts), following this repo's existing convention of
// testing the real request/response contract a component's handlers call
// (no React Testing Library is configured in this repo -- see
// tests/entitlement-admin.test.ts / tests/subscription.test.ts, which test
// lib/api and pure helper functions directly rather than mounting
// components). Covers: submit (invite), success shape, loading resolution
// (the promise the panel's setInviteBusy/finally depends on), API failure
// normalization (what inviteError.message renders), revoke submit/success,
// and the authorization-failure / conflict display paths the panel shows
// for both invite and revoke.

const ACCESS_TOKEN = "test-access-token";
const ORG_ID = "11111111-1111-1111-1111-111111111111";
const USER_ID = "22222222-2222-2222-2222-222222222222";

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValueOnce({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

describe("platformApi invitation panel (M19.1 invite / M19.2 revoke)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("submits an invite with only email + full_name (no password field) and returns the created admin's id", async () => {
    const responseBody = {
      id: USER_ID,
      email: "new-admin@example.com",
      full_name: "New Admin",
      onboarding_email_sent: true,
    };
    const fetchMock = mockFetchOnce(201, responseBody);
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await platformApi.inviteOrganizationAdmin(ACCESS_TOKEN, ORG_ID, {
      email: "new-admin@example.com",
      full_name: "New Admin",
    });

    expect(result).toEqual(responseBody);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain(`/platform/organizations/${ORG_ID}/invite-admin`);
    expect(init.method).toBe("POST");
    const sentBody = JSON.parse(init.body as string);
    expect(sentBody).toEqual({ email: "new-admin@example.com", full_name: "New Admin" });
    expect(sentBody.password).toBeUndefined();
    expect(init.headers.Authorization).toBe(`Bearer ${ACCESS_TOKEN}`);
  });

  it("reports onboarding_email_sent: false without throwing, so the panel can show the degraded-success message", async () => {
    const responseBody = {
      id: USER_ID,
      email: "no-email@example.com",
      full_name: "No Email",
      onboarding_email_sent: false,
    };
    global.fetch = mockFetchOnce(201, responseBody) as unknown as typeof fetch;

    const result = await platformApi.inviteOrganizationAdmin(ACCESS_TOKEN, ORG_ID, {
      email: "no-email@example.com",
      full_name: "No Email",
    });

    expect(result.onboarding_email_sent).toBe(false);
  });

  it("normalizes a duplicate-email invite failure (409) into the panel's conflict message, not a raw error", async () => {
    global.fetch = mockFetchOnce(409, {
      error: { code: "conflict", message: "A user with this email already exists" },
    }) as unknown as typeof fetch;

    await expect(
      platformApi.inviteOrganizationAdmin(ACCESS_TOKEN, ORG_ID, {
        email: "dup@example.com",
        full_name: "Dup",
      })
    ).rejects.toBeInstanceOf(ApiError);

    global.fetch = mockFetchOnce(409, {
      error: { code: "conflict", message: "A user with this email already exists" },
    }) as unknown as typeof fetch;

    try {
      await platformApi.inviteOrganizationAdmin(ACCESS_TOKEN, ORG_ID, {
        email: "dup@example.com",
        full_name: "Dup",
      });
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("conflict");
      expect(normalized.message).toBe("A user with this email already exists");
    }
  });

  it("normalizes an unauthorized-invite attempt (403, e.g. an ORG_ADMIN caller) into the panel's forbidden message", async () => {
    global.fetch = mockFetchOnce(403, {
      error: { code: "forbidden", message: "Missing required permission: platform:manage" },
    }) as unknown as typeof fetch;

    try {
      await platformApi.inviteOrganizationAdmin(ACCESS_TOKEN, ORG_ID, {
        email: "blocked@example.com",
        full_name: "Blocked",
      });
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("forbidden");
    }
  });

  it("submits a revoke against the invited admin's user id and surfaces the success message", async () => {
    const fetchMock = mockFetchOnce(200, { message: "Invitation revoked." });
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await platformApi.revokeAdminInvitation(ACCESS_TOKEN, USER_ID);

    expect(result).toEqual({ message: "Invitation revoked." });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain(`/platform/admins/${USER_ID}/revoke-invitation`);
    expect(init.method).toBe("POST");
  });

  it("normalizes revoking an already-accepted/already-revoked invitation (409) so the panel shows a conflict, not a crash", async () => {
    global.fetch = mockFetchOnce(409, {
      error: { code: "no_pending_invitation", message: "There is no pending invitation to revoke for this user." },
    }) as unknown as typeof fetch;

    try {
      await platformApi.revokeAdminInvitation(ACCESS_TOKEN, USER_ID);
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("conflict");
      expect(normalized.message).toBe("There is no pending invitation to revoke for this user.");
    }
  });

  it("normalizes revoking a nonexistent user (404)", async () => {
    global.fetch = mockFetchOnce(404, {
      error: { code: "not_found", message: "User not found" },
    }) as unknown as typeof fetch;

    try {
      await platformApi.revokeAdminInvitation(ACCESS_TOKEN, "99999999-9999-9999-9999-999999999999");
      throw new Error("expected rejection");
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("not_found");
    }
  });
});
