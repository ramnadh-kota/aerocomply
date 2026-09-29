import { describe, it, expect } from "vitest";
import {
  INGESTABLE_CONNECTORS,
  acceptanceRate,
  canDelete,
  canIngest,
  formatAge,
  formatLatency,
  lifecycleActions,
  parseConnectionConfig,
  HEALTH_BADGE,
} from "../lib/data-sources/helpers";
import { getRouteFeatureKey } from "../lib/entitlements/navFeatureMap";

describe("data source lifecycle", () => {
  it("offers only the legal next transitions", () => {
    expect(lifecycleActions("DRAFT").map((a) => a.to)).toEqual(["ACTIVE"]);
    expect(lifecycleActions("ACTIVE").map((a) => a.to)).toEqual(["PAUSED", "DECOMMISSIONED"]);
    expect(lifecycleActions("PAUSED").map((a) => a.to)).toEqual(["ACTIVE", "DECOMMISSIONED"]);
    expect(lifecycleActions("DECOMMISSIONED")).toEqual([]);
  });

  it("allows deleting only DRAFT or DECOMMISSIONED sources (mirrors the backend rule)", () => {
    expect(canDelete("DRAFT")).toBe(true);
    expect(canDelete("DECOMMISSIONED")).toBe(true);
    expect(canDelete("ACTIVE")).toBe(false);
    expect(canDelete("PAUSED")).toBe(false);
  });

  it("only ACTIVE sources of an ingestable connector can receive data", () => {
    expect(canIngest({ status: "ACTIVE", connector_type: "CSV_BATCH" })).toBe(true);
    expect(canIngest({ status: "PAUSED", connector_type: "CSV_BATCH" })).toBe(false);
    expect(canIngest({ status: "DRAFT", connector_type: "MQTT" })).toBe(false);
    expect(canIngest({ status: "ACTIVE", connector_type: "DJI_FLIGHTHUB" })).toBe(false);
    expect(canIngest({ status: "ACTIVE", connector_type: "OEM_API" })).toBe(false);
    expect(INGESTABLE_CONNECTORS.has("MAVLINK")).toBe(true);
  });
});

describe("connection config editor", () => {
  it("treats empty input as an empty config", () => {
    expect(parseConnectionConfig("  ")).toEqual({ ok: true, value: {} });
  });

  it("rejects invalid JSON and non-objects", () => {
    expect(parseConnectionConfig("{nope")).toMatchObject({ ok: false });
    expect(parseConnectionConfig("[1,2]")).toMatchObject({ ok: false });
    expect(parseConnectionConfig('"str"')).toMatchObject({ ok: false });
  });

  it("refuses credentials at any depth before the backend has to 422", () => {
    const top = parseConnectionConfig('{"broker":"x","password":"hunter2"}');
    expect(top).toMatchObject({ ok: false });
    if (!top.ok) expect(top.error).toContain("connection_config.password");
    const nested = parseConnectionConfig('{"auth":{"api_key":"k"}}');
    expect(nested).toMatchObject({ ok: false });
    if (!nested.ok) expect(nested.error).toContain("connection_config.auth.api_key");
  });

  it("accepts a normal MAVLink mapping", () => {
    const r = parseConnectionConfig('{"system_id_map":{"1":"abc"},"expected_interval_seconds":10}');
    expect(r).toEqual({ ok: true, value: { system_id_map: { "1": "abc" }, expected_interval_seconds: 10 } });
  });
});

describe("health presentation", () => {
  it("maps every backend health state to a labelled badge (never colour alone)", () => {
    for (const k of ["HEALTHY", "DEGRADED", "FAILED", "INACTIVE"] as const) {
      expect(HEALTH_BADGE[k].label.length).toBeGreaterThan(0);
    }
    expect(HEALTH_BADGE.FAILED.kind).toBe("NON_COMPLIANT");
  });

  it("reports 'never' when there is no evidence rather than inventing a time", () => {
    expect(formatAge(null)).toBe("never");
    expect(formatAge(undefined)).toBe("never");
  });

  it("formats ages relative to now", () => {
    const now = new Date("2026-01-01T12:00:00Z");
    expect(formatAge("2026-01-01T11:59:30Z", now)).toBe("30s ago");
    expect(formatAge("2026-01-01T11:00:00Z", now)).toBe("1h ago");
    expect(formatAge("2025-12-30T12:00:00Z", now)).toBe("2d ago");
  });

  it("formats latency and treats missing as unknown", () => {
    expect(formatLatency(null)).toBe("—");
    expect(formatLatency(250)).toBe("250 ms");
    expect(formatLatency(2500)).toBe("2.5 s");
  });

  it("acceptance rate is null with no evidence and a ratio otherwise", () => {
    expect(acceptanceRate({ event_count: 0, error_count: 0, quarantined_count: 0 })).toBeNull();
    expect(acceptanceRate({ event_count: 3, error_count: 1, quarantined_count: 0 })).toBe(0.75);
  });
});

describe("route protection", () => {
  it("the data sources page is gated by the telemetry feature like the ingest API", () => {
    expect(getRouteFeatureKey("/data-sources")).toBe("flight_telemetry");
    expect(getRouteFeatureKey("/data-sources/anything")).toBe("flight_telemetry");
  });
});
