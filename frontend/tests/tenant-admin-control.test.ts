import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { tenantApi } from "../lib/api/tenant";
import {
  DEMO_TENANT_PROFILE,
  DEMO_TENANT_USERS,
  DEMO_TENANT_INVITATIONS,
  DEMO_TENANT_ROLES,
  DEMO_TENANT_TEAMS,
  DEMO_TENANT_USAGE,
  DEMO_TENANT_DASHBOARD_STATS,
} from "../lib/demo/demoTenant";

const ACCESS_TOKEN = "test-tenant-token";
const USER_ID = "00000000-0000-0000-0000-000000000014";

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValueOnce({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

describe("tenantApi Client (M3 Tenant Administration)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("getDashboard calls /tenant/dashboard with auth token", async () => {
    const fetchMock = mockFetchOnce(200, DEMO_TENANT_DASHBOARD_STATS);
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await tenantApi.getDashboard(ACCESS_TOKEN);
    expect(result.organization.name).toBe(DEMO_TENANT_PROFILE.name);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/tenant/dashboard");
    expect(init.headers["Authorization"]).toBe(`Bearer ${ACCESS_TOKEN}`);
  });

  it("updateProfile sends PATCH to /tenant/profile with serialized payload", async () => {
    const updatedProfile = { ...DEMO_TENANT_PROFILE, name: "Updated Aero Logistics" };
    const fetchMock = mockFetchOnce(200, updatedProfile);
    global.fetch = fetchMock as unknown as typeof fetch;

    const result = await tenantApi.updateProfile(ACCESS_TOKEN, {
      name: "Updated Aero Logistics",
    });
    expect(result.name).toBe("Updated Aero Logistics");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/tenant/profile");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ name: "Updated Aero Logistics" });
  });

  it("updateUserRoles sends PATCH to /tenant/users/{id}/roles", async () => {
    const fetchMock = mockFetchOnce(200, { id: USER_ID, roles: ["MAINTENANCE_ENGINEER"] });
    global.fetch = fetchMock as unknown as typeof fetch;

    await tenantApi.updateUserRoles(ACCESS_TOKEN, USER_ID, ["MAINTENANCE_ENGINEER"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain(`/tenant/users/${USER_ID}/roles`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ roles: ["MAINTENANCE_ENGINEER"] });
  });

  it("inviteUser sends POST to /tenant/invitations with role and email", async () => {
    const invitePayload = {
      email: "engineer@aerocomply.com",
      full_name: "Test Engineer",
      role: "MAINTENANCE_ENGINEER",
    };
    const fetchMock = mockFetchOnce(201, { id: "inv-1", ...invitePayload, status: "PENDING" });
    global.fetch = fetchMock as unknown as typeof fetch;

    await tenantApi.inviteUser(ACCESS_TOKEN, invitePayload);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/tenant/invitations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(invitePayload);
  });

  it("cancelInvitation sends POST to /tenant/invitations/{id}/cancel", async () => {
    const fetchMock = mockFetchOnce(200, { message: "Invitation cancelled." });
    global.fetch = fetchMock as unknown as typeof fetch;

    await tenantApi.cancelInvitation(ACCESS_TOKEN, USER_ID);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain(`/tenant/invitations/${USER_ID}/cancel`);
    expect(init.method).toBe("POST");
  });
});

describe("DEMO Dataset Integrity (M3 Tenant Administration)", () => {
  it("DEMO_TENANT_PROFILE represents active customer tenant without platform fields", () => {
    expect(DEMO_TENANT_PROFILE.status).toBe("ACTIVE");
    expect(DEMO_TENANT_PROFILE.name).toBe("KOTA Aerospace Demo Operations");
    expect(DEMO_TENANT_PROFILE.industry).toBe("AIRCRAFT");
  });

  it("DEMO_TENANT_ROLES strictly excludes platform administration roles", () => {
    const roleNames = DEMO_TENANT_ROLES.map((r) => r.role_name);
    expect(roleNames).not.toContain("PLATFORM_ADMIN");
    expect(roleNames).not.toContain("PLATFORM_STAFF");
    expect(roleNames).toContain("ORG_ADMIN");
    expect(roleNames).toContain("CAMO_MANAGER");
    expect(roleNames).toContain("MAINTENANCE_ENGINEER");
    expect(roleNames).toContain("VIEWER");
  });

  it("DEMO_TENANT_USAGE honestly identifies unmetered dimensions as NOT_TRACKED", () => {
    const unmetered = DEMO_TENANT_USAGE.metrics.filter((m) => !m.tracked);
    expect(unmetered.length).toBeGreaterThanOrEqual(3);
    for (const m of unmetered) {
      expect(m.status).toBe("NOT_TRACKED");
      expect(m.value).toBeNull();
    }

    const tracked = DEMO_TENANT_USAGE.metrics.filter((m) => m.tracked);
    expect(tracked.length).toBeGreaterThanOrEqual(4);
    for (const m of tracked) {
      expect(m.status).toBe("TRACKED");
      expect(m.value).not.toBeNull();
    }
  });

  it("DEMO_TENANT_TEAMS organizes personnel by aerospace operational discipline", () => {
    const teamNames = DEMO_TENANT_TEAMS.map((t) => t.name);
    expect(teamNames).toContain("Organization Administration");
    expect(teamNames).toContain("Maintenance & CAMO");
    expect(teamNames).toContain("Quality & Inspection");
    expect(teamNames).toContain("Regulatory & Safety Compliance");
    expect(teamNames).toContain("Stakeholders & Viewers");
  });
});
