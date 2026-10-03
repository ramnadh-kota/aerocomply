import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { authApi, normalizeApiError, getApiBaseUrl } from "../lib/apiClient";

// Login resilience: one automatic retry for a genuine network-level failure
// (fetch() throwing, or our own timeout), never for a completed HTTP response.

function jsonResponse(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

describe("authApi.login resilience", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("A. succeeds on the first attempt without retrying", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, { access_token: "a", refresh_token: "r", token_type: "bearer" })
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await authApi.login("user@example.com", "correct-password");

    expect(result.access_token).toBe("a");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("B. invalid credentials (401) are not retried and classify as unauthorized", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(401, { error: { code: "invalid_credentials", message: "Invalid email or password." } })
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(authApi.login("user@example.com", "wrong")).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    try {
      await authApi.login("user@example.com", "wrong");
    } catch (err) {
      expect(normalizeApiError(err)).toMatchObject({ kind: "unauthorized", message: "Invalid email or password." });
    }
  });

  it("C. validation error (422) is not retried", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(422, { error: { code: "validation_error", message: "Invalid input." } })
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      await authApi.login("not-an-email", "x");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("validation");
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("D. server error (500) is not retried and classifies as server error", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500, { error: { code: "internal", message: "boom" } }));
    vi.stubGlobal("fetch", fetchMock);

    try {
      await authApi.login("user@example.com", "x");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("server");
    }
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("E. a transient network failure followed by success still logs in", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "a2", refresh_token: "r2", token_type: "bearer" }));
    vi.stubGlobal("fetch", fetchMock);

    const onRetry = vi.fn();
    const promise = authApi.login("user@example.com", "correct-password", { onRetry });
    await vi.runAllTimersAsync();
    const result = await promise;

    expect(result.access_token).toBe("a2");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("F. two consecutive network failures surface the existing offline message", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);

    const promise = authApi.login("user@example.com", "correct-password");
    const assertion = expect(promise).rejects.toBeInstanceOf(TypeError);
    await vi.runAllTimersAsync();
    await assertion;
    expect(fetchMock).toHaveBeenCalledTimes(2);

    try {
      const p2 = authApi.login("user@example.com", "correct-password");
      const done = p2.catch((e) => e);
      await vi.runAllTimersAsync();
      const err = await done;
      expect(normalizeApiError(err)).toMatchObject({
        kind: "offline",
        message: "Unable to reach the server. Check your connection and try again.",
      });
    } finally {
      // no-op
    }
  });

  it("G. a timeout is handled as a network/offline error, never as invalid credentials", async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () => {
          const abortErr = new DOMException("The operation was aborted.", "AbortError");
          reject(abortErr);
        });
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const promise = authApi.login("user@example.com", "correct-password");
    const done = promise.catch((e) => e);
    await vi.runAllTimersAsync();
    const err = await done;

    expect(normalizeApiError(err).kind).toBe("offline");
    expect(normalizeApiError(err).message).not.toMatch(/invalid/i);
    // one timeout + one retry, both timing out
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("H. a duplicate (double-click) login call while one is in flight does not start a second real request beyond the caller's own guard", async () => {
    let resolveFirst: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveFirst = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    const first = authApi.login("user@example.com", "correct-password");
    // Simulate the UI's own guard: a second call is never issued while `first` is pending
    // (see app/login/page.tsx's `if (loading) return;`), so only one fetch is in flight.
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveFirst(jsonResponse(200, { access_token: "a3", refresh_token: "r3", token_type: "bearer" }));
    await first;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("I. server unavailable (503) maps to unavailable message", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(503, { error: { code: "service_unavailable", message: "Server overloaded" } })
    );
    vi.stubGlobal("fetch", fetchMock);

    try {
      await authApi.login("user@example.com", "correct-password");
      expect.unreachable();
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("server");
      expect(normalized.message).toBe("The server is temporarily unavailable. Please try again shortly.");
    }
  });
});

describe("getApiBaseUrl resolution", () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_BASE_URL;

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = originalEnv;
    vi.unstubAllGlobals();
  });

  it("resolves to NEXT_PUBLIC_API_BASE_URL when set in environment", () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://custom-api.example.com/api/v1/";
    expect(getApiBaseUrl()).toBe("https://custom-api.example.com/api/v1");
  });

  it("resolves to Render staging on Vercel preview hostnames when env is unset", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    vi.stubGlobal("window", {
      location: { hostname: "aerocomply-ct196idr4-ram-ee15.vercel.app" },
    });
    expect(getApiBaseUrl()).toBe("https://aerocomply-backend-staging.onrender.com/api/v1");
  });

  it("resolves to Render staging on Vercel production hostname when env is unset", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    vi.stubGlobal("window", {
      location: { hostname: "aerocomply.vercel.app" },
    });
    expect(getApiBaseUrl()).toBe("https://aerocomply-backend-staging.onrender.com/api/v1");
  });

  it("resolves to Render staging on admin.kotaaerospace.com when env is unset", () => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    vi.stubGlobal("window", {
      location: { hostname: "admin.kotaaerospace.com" },
    });
    expect(getApiBaseUrl()).toBe("https://aerocomply-backend-staging.onrender.com/api/v1");
  });
});
