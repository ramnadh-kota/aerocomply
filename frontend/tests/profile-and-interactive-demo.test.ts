import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { authApi } from "../lib/apiClient";
import { demoStore } from "../lib/demo/demoStore";
import {
  getDemoAssetDetail,
  getDemoConfiguration,
  getDemoReadiness,
} from "../lib/demo/demoAssets";

const ACCESS_TOKEN = "test-jwt-token";

function mockFetchOnce(status: number, body: unknown) {
  return vi.fn().mockResolvedValueOnce({
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  });
}

describe("Profile & Authentication API", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("authApi.updateMe sends PATCH to /api/v1/auth/me with full_name and phone_number payload", async () => {
    const updatedUser = {
      id: "usr-123",
      email: "engineer@aerocomply.com",
      full_name: "Captain Ramnadh",
      phone_number: "+91 98765 43210",
      roles: ["CHIEF_PILOT"],
      organization_id: "org-123",
      email_verified: true,
    };

    const fetchMock = mockFetchOnce(200, updatedUser);
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await authApi.updateMe(ACCESS_TOKEN, {
      full_name: "Captain Ramnadh",
      phone_number: "+91 98765 43210",
    });
    expect(res.full_name).toBe("Captain Ramnadh");
    expect(res.phone_number).toBe("+91 98765 43210");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/auth/me");
    expect(init.method).toBe("PATCH");
    expect(init.headers["Authorization"]).toBe(`Bearer ${ACCESS_TOKEN}`);
    expect(JSON.parse(init.body)).toEqual({
      full_name: "Captain Ramnadh",
      phone_number: "+91 98765 43210",
    });
  });

  it("authApi.updateMe throws error on non-200 response", async () => {
    const fetchMock = mockFetchOnce(400, { detail: "Invalid full name" });
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(authApi.updateMe(ACCESS_TOKEN, { full_name: "" })).rejects.toThrow();
  });

  it("authApi.deletePhoto sends DELETE to /api/v1/auth/me/photo", async () => {
    const userWithoutPhoto = {
      id: "usr-123",
      email: "pilot@aerocomply.com",
      full_name: "Captain Vikram",
      profile_photo_url: null,
      roles: ["VIEWER"],
      organization_id: "org-123",
      email_verified: true,
    };

    const fetchMock = mockFetchOnce(200, userWithoutPhoto);
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await authApi.deletePhoto(ACCESS_TOKEN);
    expect(res.profile_photo_url).toBeNull();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/auth/me/photo");
    expect(init.method).toBe("DELETE");
    expect(init.headers["Authorization"]).toBe(`Bearer ${ACCESS_TOKEN}`);
  });

  it("authApi.requestEmailChange sends POST to /api/v1/auth/me/change-email/request", async () => {
    const responsePayload = { message: "Verification code sent to new@aerocomply.com" };
    const fetchMock = mockFetchOnce(200, responsePayload);
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await authApi.requestEmailChange(ACCESS_TOKEN, "new@aerocomply.com");
    expect(res.message).toBe("Verification code sent to new@aerocomply.com");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/auth/me/change-email/request");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ new_email: "new@aerocomply.com" });
  });

  it("authApi.confirmEmailChange sends POST to /api/v1/auth/me/change-email/confirm", async () => {
    const updatedUser = {
      id: "usr-123",
      email: "new@aerocomply.com",
      pending_email: null,
      email_verified: true,
      roles: ["ADMIN"],
      organization_id: "org-123",
      full_name: "Captain Vikram",
    };
    const fetchMock = mockFetchOnce(200, updatedUser);
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await authApi.confirmEmailChange(ACCESS_TOKEN, "123456");
    expect(res.email).toBe("new@aerocomply.com");
    expect(res.pending_email).toBeNull();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/auth/me/change-email/confirm");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ code: "123456" });
  });

  it("authApi.cancelEmailChange sends POST to /api/v1/auth/me/change-email/cancel", async () => {
    const cancelledUser = {
      id: "usr-123",
      email: "old@aerocomply.com",
      pending_email: null,
      email_verified: true,
      roles: ["ADMIN"],
      organization_id: "org-123",
      full_name: "Captain Vikram",
    };
    const fetchMock = mockFetchOnce(200, cancelledUser);
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await authApi.cancelEmailChange(ACCESS_TOKEN);
    expect(res.pending_email).toBeNull();
    expect(res.email).toBe("old@aerocomply.com");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/auth/me/change-email/cancel");
    expect(init.method).toBe("POST");
  });
});

describe("Interactive Demo Store (Profile Simulation)", () => {
  beforeEach(() => {
    demoStore.reset();
  });

  it("supports updating demo user profile with session persistence", () => {
    expect(demoStore.getProfile()).toBeNull();

    demoStore.updateProfile({
      full_name: "Demo Chief Inspector",
      phone_number: "+91 99999 88888",
      profile_photo_url: "data:image/png;base64,demo",
    });

    const prof = demoStore.getProfile();
    expect(prof).not.toBeNull();
    expect(prof?.full_name).toBe("Demo Chief Inspector");
    expect(prof?.phone_number).toBe("+91 99999 88888");
    expect(prof?.profile_photo_url).toBe("data:image/png;base64,demo");
  });
});

describe("Interactive Demo Store (Isolation & Interactivity)", () => {
  beforeEach(() => {
    demoStore.reset();
  });

  it("initializes with baseline demo assets and stats", () => {
    const assets = demoStore.getAssets();
    expect(assets.length).toBeGreaterThanOrEqual(5);

    const stats = demoStore.getDashboardStats();
    expect(stats.fleet_count).toBe(assets.length);
    expect(stats.aircraft_count).toBe(assets.filter((a) => a.asset_type === "AIRCRAFT").length);
    expect(stats.drone_count).toBe(assets.filter((a) => a.asset_type === "DRONE").length);
  });

  it("allows creating a new Drone asset and mirrors into demo drone fleet", () => {
    const initialAssets = demoStore.getAssets().length;
    const initialDrones = demoStore.getDrones().length;
    const initialDroneStats = demoStore.getDashboardStats().drone_count;

    const created = demoStore.addAsset({
      asset_type: "DRONE",
      registration: "VT-TEST-DRN",
      manufacturer: "KOTA Aerospace",
      model: "SkySurveyor Pro",
      serial_number: "SN-999-DRN",
      status: "ACTIVE",
    });

    expect(created.id).toBeDefined();
    expect(created.asset_type).toBe("DRONE");
    expect(created.registration).toBe("VT-TEST-DRN");

    // Verify assets collection updated
    const updatedAssets = demoStore.getAssets();
    expect(updatedAssets.length).toBe(initialAssets + 1);
    expect(updatedAssets[0].registration).toBe("VT-TEST-DRN");

    // Verify drones collection mirrored
    const updatedDrones = demoStore.getDrones();
    expect(updatedDrones.length).toBe(initialDrones + 1);
    expect(updatedDrones[0].registration).toBe("VT-TEST-DRN");

    // Verify stats dynamically updated
    const stats = demoStore.getDashboardStats();
    expect(stats.fleet_count).toBe(initialAssets + 1);
    expect(stats.drone_count).toBe(initialDroneStats + 1);
  });

  it("allows creating a Fixed-Wing Aircraft asset without polluting drone collection", () => {
    const initialDrones = demoStore.getDrones().length;
    const initialAircraftStats = demoStore.getDashboardStats().aircraft_count;

    const created = demoStore.addAsset({
      asset_type: "AIRCRAFT",
      registration: "VT-AIR-01",
      manufacturer: "Airbus",
      model: "A350-900",
      serial_number: "MSN-50123",
      status: "IN_SERVICE",
    });

    expect(created.asset_type).toBe("AIRCRAFT");
    expect(created.registration).toBe("VT-AIR-01");

    // Drones count should remain unchanged
    expect(demoStore.getDrones().length).toBe(initialDrones);

    const stats = demoStore.getDashboardStats();
    expect(stats.aircraft_count).toBe(initialAircraftStats + 1);
  });

  it("allows creating a Helicopter / Rotorcraft asset", () => {
    const created = demoStore.addAsset({
      asset_type: "HELICOPTER",
      registration: "VT-HELI-99",
      manufacturer: "Bell",
      model: "429 GlobalRanger",
      serial_number: "SN-HELI-88",
    });

    expect(created.asset_type).toBe("HELICOPTER");
    expect(created.registration).toBe("VT-HELI-99");
    expect(demoStore.getAssetById(created.id)?.model).toBe("429 GlobalRanger");
  });

  it("allows updating an existing demo asset", () => {
    const assets = demoStore.getAssets();
    const target = assets[0];

    const updated = demoStore.updateAsset(target.id, {
      status: "MAINTENANCE",
      model: "Upgraded Variant",
    });

    expect(updated).not.toBeNull();
    expect(updated?.status).toBe("MAINTENANCE");
    expect(updated?.model).toBe("Upgraded Variant");

    const fetched = demoStore.getAssetById(target.id);
    expect(fetched?.status).toBe("MAINTENANCE");
  });

  it("generates complete M4 asset detail for newly created demo assets", () => {
    const created = demoStore.addAsset({
      asset_type: "AIRCRAFT",
      registration: "VT-NEW-JET",
      manufacturer: "Boeing",
      model: "787-9",
    });

    const detail = getDemoAssetDetail(created.id);
    expect(detail).toBeDefined();
    expect(detail?.registration).toBe("VT-NEW-JET");
    expect(detail?.asset_type).toBe("AIRCRAFT");

    const config = getDemoConfiguration(created.id);
    expect(config).toBeDefined();
    expect(config.asset_type).toBe("AIRCRAFT");

    const readiness = getDemoReadiness(created.id);
    expect(readiness).toBeDefined();
    expect(readiness.overall_status).toBe("READY");
  });

  it("handles demo member invitation lifecycle with simulation isolation", () => {
    const initialInvCount = demoStore.getInvitations().length;

    const inv = demoStore.addInvitation({
      email: "safety.inspector@skytest.com",
      role_id: "00000000-0000-0000-0000-000000000022",
      role_name: "Safety Inspector",
    });

    expect(inv.id).toBeDefined();
    expect(inv.email).toBe("safety.inspector@skytest.com");
    expect(inv.status).toBe("PENDING");
    expect(inv.can_cancel).toBe(true);

    const updatedInvs = demoStore.getInvitations();
    expect(updatedInvs.length).toBe(initialInvCount + 1);

    // Test resend simulation
    const resendSuccess = demoStore.resendInvitation(inv.id);
    expect(resendSuccess).toBe(true);

    // Test cancel simulation
    const cancelSuccess = demoStore.cancelInvitation(inv.id);
    expect(cancelSuccess).toBe(true);

    const cancelledInv = demoStore.getInvitations().find((i) => i.id === inv.id);
    expect(cancelledInv?.status).toBe("CANCELLED");
    expect(cancelledInv?.can_cancel).toBe(false);
  });

  it("notifies listeners reactively on store mutations", () => {
    let callCount = 0;
    const unsubscribe = demoStore.subscribe(() => {
      callCount++;
    });

    demoStore.addAsset({
      asset_type: "DRONE",
      registration: "VT-EVT-01",
    });

    expect(callCount).toBe(1);

    demoStore.addInvitation({
      email: "colleague@aerocomply.com",
    });

    expect(callCount).toBe(2);

    unsubscribe();

    demoStore.addAsset({
      asset_type: "DRONE",
      registration: "VT-EVT-02",
    });

    // Should not increment after unsubscribe
    expect(callCount).toBe(2);
  });
});
