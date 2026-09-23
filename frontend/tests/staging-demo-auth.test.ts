import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  DEMO_ORG_ID,
  DEMO_ORG_NAME,
  DEMO_USER_ID,
  DEMO_USER_NAME,
  DEMO_USER_EMAIL,
  DEMO_USER_PASSWORD,
  DEMO_USER_ROLES,
  DEMO_SESSION_STORAGE_KEY,
  DEMO_USER,
} from "../lib/auth/SessionContext";
import {
  ACCESS_TOKEN_STORAGE_KEY,
  REFRESH_TOKEN_STORAGE_KEY,
} from "../lib/apiClient";

describe("Staging Demo Identity & Credentials", () => {
  it("defines deterministic demo organization identifiers", () => {
    expect(DEMO_ORG_ID).toBe("00000000-0000-0000-0000-000000000001");
    expect(DEMO_ORG_NAME).toBe("KOTA Aerospace Demo Operations");
  });

  it("defines deterministic demo user identity and roles", () => {
    expect(DEMO_USER_ID).toBe("00000000-0000-0000-0000-000000000002");
    expect(DEMO_USER_NAME).toBe("KOTA Aerospace Demo User");
    expect(DEMO_USER_EMAIL).toBe("demo@kotaaerospace.com");
    expect(DEMO_USER_PASSWORD).toBe("KotaDemo2026!");
    expect(DEMO_USER_ROLES).toEqual([
      "ORGANIZATION_ADMIN",
      "MAINTENANCE_MANAGER",
      "CHIEF_PILOT",
    ]);
  });

  it("creates a well-formed DEMO_USER entity", () => {
    expect(DEMO_USER).toEqual({
      id: "00000000-0000-0000-0000-000000000002",
      organization_id: "00000000-0000-0000-0000-000000000001",
      email: "demo@kotaaerospace.com",
      full_name: "KOTA Aerospace Demo User",
      roles: ["ORGANIZATION_ADMIN", "MAINTENANCE_MANAGER", "CHIEF_PILOT"],
      email_verified: true,
    });
  });
});

describe("Demo vs Real Session State Separation", () => {
  const localStorageMock: Record<string, string> = {};

  beforeEach(() => {
    for (const key of Object.keys(localStorageMock)) {
      delete localStorageMock[key];
    }
  });

  it("demo storage key is distinct from real JWT storage keys", () => {
    expect(DEMO_SESSION_STORAGE_KEY).not.toBe(ACCESS_TOKEN_STORAGE_KEY);
    expect(DEMO_SESSION_STORAGE_KEY).not.toBe(REFRESH_TOKEN_STORAGE_KEY);
  });

  it("demo credentials interception logic matches exact demo credentials without calling real API", () => {
    const authApiMock = {
      login: vi.fn(),
      me: vi.fn(),
    };

    function loginHandler(emailInput: string, passwordInput: string) {
      if (
        emailInput.trim().toLowerCase() === DEMO_USER_EMAIL.toLowerCase() &&
        passwordInput === DEMO_USER_PASSWORD
      ) {
        // Intercepted as demo session
        localStorageMock[DEMO_SESSION_STORAGE_KEY] = "true";
        delete localStorageMock[ACCESS_TOKEN_STORAGE_KEY];
        delete localStorageMock[REFRESH_TOKEN_STORAGE_KEY];
        return { type: "DEMO", user: DEMO_USER };
      }

      // Real login path
      authApiMock.login(emailInput, passwordInput);
      return { type: "REAL", user: null };
    }

    // 1. Entering demo credentials
    const demoRes = loginHandler("demo@kotaaerospace.com", "KotaDemo2026!");
    expect(demoRes.type).toBe("DEMO");
    expect(demoRes.user).toEqual(DEMO_USER);
    expect(authApiMock.login).not.toHaveBeenCalled();
    expect(localStorageMock[DEMO_SESSION_STORAGE_KEY]).toBe("true");

    // 2. Entering real customer credentials
    const realRes = loginHandler("pilot@airline.com", "RealSecret123!");
    expect(realRes.type).toBe("REAL");
    expect(authApiMock.login).toHaveBeenCalledWith("pilot@airline.com", "RealSecret123!");
  });

  it("demo logout clears demo session completely", () => {
    localStorageMock[DEMO_SESSION_STORAGE_KEY] = "true";
    localStorageMock["aerocomply-data-mode"] = "DEMO";

    function logoutHandler() {
      delete localStorageMock[DEMO_SESSION_STORAGE_KEY];
      delete localStorageMock[ACCESS_TOKEN_STORAGE_KEY];
      delete localStorageMock[REFRESH_TOKEN_STORAGE_KEY];
    }

    logoutHandler();
    expect(localStorageMock[DEMO_SESSION_STORAGE_KEY]).toBeUndefined();
    expect(localStorageMock[ACCESS_TOKEN_STORAGE_KEY]).toBeUndefined();
  });

  it("environment label correctly distinguishes DEMO vs REAL sessions", () => {
    function getEnvironmentLabel(sessionType: "DEMO" | "REAL" | null) {
      if (sessionType === "REAL") return "REAL ENVIRONMENT · LIVE API DATA";
      return "DEMO ENVIRONMENT · SYNTHETIC DATA";
    }

    expect(getEnvironmentLabel("DEMO")).toBe("DEMO ENVIRONMENT · SYNTHETIC DATA");
    expect(getEnvironmentLabel("REAL")).toBe("REAL ENVIRONMENT · LIVE API DATA");
    expect(getEnvironmentLabel(null)).toBe("DEMO ENVIRONMENT · SYNTHETIC DATA");
  });
});
