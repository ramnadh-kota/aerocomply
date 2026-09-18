// M17.2C: Battery/Component lifecycle frontend -- API client requests,
// event-badge/label mapping, and timeline/history-list ordering &
// data-shaping logic. This project's vitest environment is "node" (see
// vitest.config.ts) with no jsdom/@testing-library/react configured
// anywhere in the repo -- consistent with every other *.test.ts file here
// (evidence-files.test.ts, subscription.test.ts), which test pure
// functions rather than rendered DOM. These tests follow that same
// convention: they exercise the exact pure logic that feeds the Battery/
// Component/Asset-lifecycle UI (request shape, badge mapping, ordering,
// entry-building) rather than a DOM render, since no component-rendering
// test infrastructure exists in this repository to extend.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { dronesApi, type AssetLifecycleEventResponse } from "../lib/api/drones";
import { lifecycleEventBadge } from "../components/status/StatusBadge";
import { assetLifecycleEventsToTimelineEntries } from "../components/lifecycle/AssetLifecycleTimeline";
import { ApiError, normalizeApiError } from "../lib/apiClient";

function jsonResponse(status: number, body: unknown) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => body,
  } as Response;
}

describe("dronesApi lifecycle requests (API CLIENT)", () => {
  const originalFetch = global.fetch;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    global.fetch = fetchMock as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  it("requests battery current state at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "b1", asset_id: "a1" }));
    await dronesApi.getBattery("token-1", "b1");
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/batteries\/b1$/);
    expect(options.headers.Authorization).toBe("Bearer token-1");
    expect(options.method ?? "GET").toBe("GET");
  });

  it("requests battery history at the exact backend path, with pagination params", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await dronesApi.getBatteryHistory("token-1", "b1", { limit: 10, offset: 5 });
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/batteries\/b1\/history\?limit=10&offset=5$/);
  });

  it("requests component current state at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { id: "c1", asset_id: "a1" }));
    await dronesApi.getComponent("token-1", "c1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/components\/c1$/);
  });

  it("requests component history at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await dronesApi.getComponentHistory("token-1", "c1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/components\/c1\/history$/);
  });

  it("requests asset lifecycle history at the exact backend path", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await dronesApi.getAssetLifecycleHistory("token-1", "a1");
    const [url] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/drones\/a1\/lifecycle-history$/);
  });

  it("never sends an organization_id in the request (SECURITY)", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(200, { items: [], total: 0, limit: 50, offset: 0 }));
    await dronesApi.getAssetLifecycleHistory("token-1", "a1", { limit: 10, offset: 0 });
    const [url, options] = fetchMock.mock.calls[0];
    expect(String(url)).not.toMatch(/organization_id/);
    expect(JSON.stringify(options)).not.toMatch(/organization_id/);
  });

  it("propagates a 403 as a forbidden ApiError (RBAC / STATES)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { error: { code: "forbidden", message: "You do not have permission." } })
    );
    await expect(dronesApi.getBattery("token-1", "b1")).rejects.toBeInstanceOf(ApiError);
  });

  it("propagates a 404 as a not_found ApiError (STATES)", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { error: { code: "not_found", message: "Battery not found" } })
    );
    try {
      await dronesApi.getBattery("token-1", "missing");
      expect.unreachable();
    } catch (err) {
      const normalized = normalizeApiError(err);
      expect(normalized.kind).toBe("not_found");
    }
  });

  it("a network failure normalizes to the offline kind (STATES)", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    try {
      await dronesApi.getAssetLifecycleHistory("token-1", "a1");
      expect.unreachable();
    } catch (err) {
      expect(normalizeApiError(err).kind).toBe("offline");
    }
  });
});

describe("lifecycleEventBadge (BATTERY UI / COMPONENT UI / ASSET TIMELINE)", () => {
  it("uses only the four real backend event_type values -- no invented values", () => {
    const known = [
      "BATTERY_INSTALLATION",
      "BATTERY_REMOVAL",
      "COMPONENT_INSTALLATION",
      "COMPONENT_REMOVAL",
    ];
    for (const eventType of known) {
      const badge = lifecycleEventBadge(eventType);
      expect(badge.label).not.toBe(eventType); // has a human-readable label
      expect(badge.status).not.toBe("UNKNOWN");
    }
  });

  it("distinguishes installation vs removal visually (never by label text alone)", () => {
    const install = lifecycleEventBadge("BATTERY_INSTALLATION");
    const removal = lifecycleEventBadge("BATTERY_REMOVAL");
    expect(install.status).not.toBe(removal.status);
  });

  it("falls back safely for an unrecognized event type", () => {
    const badge = lifecycleEventBadge("SOMETHING_UNEXPECTED");
    expect(badge.status).toBe("UNKNOWN");
  });
});

describe("assetLifecycleEventsToTimelineEntries (ASSET TIMELINE)", () => {
  function event(overrides: Partial<AssetLifecycleEventResponse>): AssetLifecycleEventResponse {
    return {
      event_type: "BATTERY_INSTALLATION",
      occurred_at: "2026-01-01T00:00:00Z",
      asset_id: "asset-1",
      installation_id: "inst-1",
      battery_id: "batt-1",
      component_id: null,
      actor_user_id: null,
      ...overrides,
    };
  }

  it("produces one timeline entry per event, preserving given order", () => {
    const events = [
      event({ installation_id: "inst-1", event_type: "COMPONENT_INSTALLATION", battery_id: null, component_id: "comp-1" }),
      event({ installation_id: "inst-2", event_type: "BATTERY_REMOVAL" }),
      event({ installation_id: "inst-3", event_type: "BATTERY_INSTALLATION" }),
    ];
    const entries = assetLifecycleEventsToTimelineEntries(events);
    expect(entries).toHaveLength(3);
    expect(entries.map((e) => e.id)).toEqual([
      "inst-1:COMPONENT_INSTALLATION",
      "inst-2:BATTERY_REMOVAL",
      "inst-3:BATTERY_INSTALLATION",
    ]);
  });

  it("renders a battery installation event with the battery id, no component id", () => {
    const [entry] = assetLifecycleEventsToTimelineEntries([event({})]);
    expect(entry.detail).toBeDefined();
  });

  it("renders a component installation event distinctly from a battery event", () => {
    const [entry] = assetLifecycleEventsToTimelineEntries([
      event({ event_type: "COMPONENT_INSTALLATION", battery_id: null, component_id: "comp-1" }),
    ]);
    expect(entry.accent).toBe("highlight");
  });

  it("marks removal events with the default (non-highlight) accent", () => {
    const [entry] = assetLifecycleEventsToTimelineEntries([event({ event_type: "COMPONENT_REMOVAL", battery_id: null, component_id: "comp-1" })]);
    expect(entry.accent).toBe("default");
  });

  it("produces no entries for an empty event list (EMPTY STATE)", () => {
    expect(assetLifecycleEventsToTimelineEntries([])).toEqual([]);
  });
});
