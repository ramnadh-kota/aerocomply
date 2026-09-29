// Pure, framework-free helpers for the Data Sources UI (unit-tested in
// tests/data-sources-helpers.test.ts). No entitlement or health logic lives here:
// the backend derives health from evidence; this only presents it.

import type { ConnectorType, DataSource, HealthStatus, SourceHealth } from "@/lib/api/dataSources";

/** Connector types that accept a pushed payload through POST /data-sources/{id}/ingest. */
export const INGESTABLE_CONNECTORS: ReadonlySet<string> = new Set<ConnectorType>([
  "MAVLINK",
  "MQTT",
  "CSV_BATCH",
  "JSON_BATCH",
  "GENERIC_WEBHOOK",
]);

export const CONNECTOR_LABELS: Record<string, string> = {
  MAVLINK: "MAVLink",
  MQTT: "MQTT",
  DJI_FLIGHTHUB: "DJI FlightHub (webhook)",
  CSV_BATCH: "CSV batch",
  JSON_BATCH: "JSON batch",
  OEM_API: "OEM API",
  GENERIC_WEBHOOK: "Generic webhook (JSON)",
};

export function canIngest(source: Pick<DataSource, "connector_type" | "status">): boolean {
  return source.status === "ACTIVE" && INGESTABLE_CONNECTORS.has(source.connector_type);
}

/** Legal next lifecycle actions (mirrors DRAFT -> ACTIVE <-> PAUSED -> DECOMMISSIONED). */
export function lifecycleActions(status: string): { label: string; to: string }[] {
  switch (status) {
    case "DRAFT":
      return [{ label: "Activate", to: "ACTIVE" }];
    case "ACTIVE":
      return [
        { label: "Pause", to: "PAUSED" },
        { label: "Decommission", to: "DECOMMISSIONED" },
      ];
    case "PAUSED":
      return [
        { label: "Resume", to: "ACTIVE" },
        { label: "Decommission", to: "DECOMMISSIONED" },
      ];
    default:
      return [];
  }
}

export function canDelete(status: string): boolean {
  return status === "DRAFT" || status === "DECOMMISSIONED";
}

export type ConfigParse = { ok: true; value: Record<string, unknown> } | { ok: false; error: string };

const SECRET_HINTS = ["password", "passwd", "secret", "token", "api_key", "apikey", "private_key", "credential"];

function findSecretKey(obj: unknown, path = "connection_config"): string | null {
  if (obj && typeof obj === "object" && !Array.isArray(obj)) {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      if (SECRET_HINTS.some((h) => k.toLowerCase().includes(h))) return `${path}.${k}`;
      const nested = findSecretKey(v, `${path}.${k}`);
      if (nested) return nested;
    }
  }
  return null;
}

/** Parses the connection-config editor. Mirrors the backend rule that credentials never go
 *  in connection_config (use secret_reference) so the user is told before a 422. */
export function parseConnectionConfig(text: string): ConfigParse {
  const trimmed = text.trim();
  if (!trimmed) return { ok: true, value: {} };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, error: "Connection config must be valid JSON." };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, error: "Connection config must be a JSON object." };
  }
  const secret = findSecretKey(parsed);
  if (secret) {
    return { ok: false, error: `${secret}: credentials must not be stored here — use the secret reference field.` };
  }
  return { ok: true, value: parsed as Record<string, unknown> };
}

export const HEALTH_BADGE: Record<
  HealthStatus,
  { kind: "COMPLIANT" | "REVIEW_REQUIRED" | "NON_COMPLIANT" | "UNKNOWN"; label: string }
> = {
  HEALTHY: { kind: "COMPLIANT", label: "Healthy" },
  DEGRADED: { kind: "REVIEW_REQUIRED", label: "Degraded" },
  FAILED: { kind: "NON_COMPLIANT", label: "Failed" },
  INACTIVE: { kind: "UNKNOWN", label: "Inactive" },
};

export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Human age ("12s ago") from an ISO timestamp; "never" when there is no evidence. */
export function formatAge(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.round((now.getTime() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

/** Share of accepted events among everything the source presented; null with no evidence. */
export function acceptanceRate(
  h: Pick<SourceHealth, "event_count" | "error_count" | "quarantined_count">
): number | null {
  const total = h.event_count + h.error_count + h.quarantined_count;
  return total === 0 ? null : h.event_count / total;
}
