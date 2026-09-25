import { describe, it, expect } from "vitest";
import * as SessionContextModule from "../lib/auth/SessionContext";

// Regression test for the removal of the client-side demo authentication bypass.
// The module must no longer export any credential, storage-key, or login-function
// that could authenticate a user without the real backend JWT flow.
describe("Demo authentication bypass removal", () => {
  it("no longer exports a demo password, session-storage key, user entity, or login function", () => {
    const mod = SessionContextModule as Record<string, unknown>;
    expect(mod.DEMO_USER_PASSWORD).toBeUndefined();
    expect(mod.DEMO_USER_ROLES).toBeUndefined();
    expect(mod.DEMO_SESSION_STORAGE_KEY).toBeUndefined();
    expect(mod.DEMO_USER).toBeUndefined();
    expect(mod.loginWithDemo).toBeUndefined();
  });

  it("still exports the demo data-labeling constants used by the synthetic-data feature", () => {
    const mod = SessionContextModule as Record<string, unknown>;
    expect(mod.DEMO_ORG_ID).toBe("00000000-0000-0000-0000-000000000001");
    expect(mod.DEMO_ORG_NAME).toBe("KOTA Aerospace Demo Operations");
    expect(mod.DEMO_USER_ID).toBe("00000000-0000-0000-0000-000000000002");
    expect(mod.DEMO_USER_NAME).toBe("KOTA Aerospace Demo User");
    // DEMO_USER_EMAIL remains as a display-only label; it is never paired with a
    // password or login path, so it cannot authenticate anyone on its own.
    expect(mod.DEMO_USER_EMAIL).toBe("demo@kotaaerospace.com");
  });
});
