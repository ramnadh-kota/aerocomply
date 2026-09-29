// Typed REAL-mode client for the DataSource acquisition API
// (backend/app/api/v1/data_sources.py). Thin by design: every rule (tenant binding,
// lifecycle, health derivation, quality gating, asset resolution) lives in the backend;
// this file only maps HTTP to typed shapes.

import { apiRequest, apiPostRaw } from "@/lib/apiClient";

export type ConnectorType =
  | "MAVLINK"
  | "MQTT"
  | "DJI_FLIGHTHUB"
  | "CSV_BATCH"
  | "JSON_BATCH"
  | "OEM_API"
  | "GENERIC_WEBHOOK";

export type DataSourceStatus = "DRAFT" | "ACTIVE" | "PAUSED" | "DECOMMISSIONED";
export type HealthStatus = "HEALTHY" | "DEGRADED" | "FAILED" | "INACTIVE";

export interface DataSource {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  connector_type: ConnectorType | string;
  connection_config: Record<string, unknown>;
  secret_reference: string | null;
  status: DataSourceStatus | string;
  default_asset_id: string | null;
  last_acquisition_at: string | null;
  last_seen_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error?: string | null;
  total_events_ingested: number;
  total_events_rejected: number;
  total_events_duplicate?: number;
  total_events_quarantined?: number;
  total_packets_lost?: number;
  latency_ms_avg?: number | null;
  consecutive_failures: number;
  created_at: string;
}

export interface DataSourceList {
  total: number;
  items: DataSource[];
}

export interface DataSourceCreate {
  name: string;
  connector_type: ConnectorType | string;
  description?: string | null;
  connection_config?: Record<string, unknown>;
  secret_reference?: string | null;
  default_asset_id?: string | null;
}

export interface DataSourceUpdate {
  name?: string;
  description?: string | null;
  connection_config?: Record<string, unknown>;
  status?: DataSourceStatus | string;
  default_asset_id?: string | null;
}

export interface SourceHealth {
  data_source_id: string;
  status: HealthStatus;
  reason: string;
  source_status: string;
  last_seen_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
  event_count: number;
  error_count: number;
  duplicate_count: number;
  quarantined_count: number;
  loss_count: number;
  latency_ms: number | null;
  consecutive_failures: number;
  evaluated_at: string;
}

export interface AcquisitionReport {
  received: number;
  accepted: number;
  duplicates: number;
  quarantined: number;
  rejected: number;
  failed: number;
  packets_lost: number;
  warnings: string[];
  errors: string[];
  latency_ms_avg: number | null;
}

export interface AcquisitionOverview {
  total_sources: number;
  by_health: Record<string, number>;
  by_connector_type: Record<string, number>;
}

const BASE = "/data-sources";

export const dataSourcesApi = {
  list: (accessToken: string) => apiRequest<DataSourceList>(`${BASE}?limit=200`, { accessToken }),
  create: (accessToken: string, body: DataSourceCreate) =>
    apiRequest<DataSource>(BASE, { method: "POST", body, accessToken }),
  update: (accessToken: string, id: string, body: DataSourceUpdate) =>
    apiRequest<DataSource>(`${BASE}/${id}`, { method: "PATCH", body, accessToken }),
  remove: (accessToken: string, id: string) =>
    apiRequest<void>(`${BASE}/${id}`, { method: "DELETE", accessToken }),
  health: (accessToken: string, id: string) =>
    apiRequest<SourceHealth>(`${BASE}/${id}/health`, { accessToken }),
  overview: (accessToken: string) =>
    apiRequest<AcquisitionOverview>(`${BASE}/stats/overview`, { accessToken }),
  /** Push a raw payload (file contents, MQTT message, MAVLink bytes) into an ACTIVE source. */
  ingest: (accessToken: string, id: string, body: BodyInit, topic?: string) =>
    apiPostRaw<AcquisitionReport>(
      `${BASE}/${id}/ingest${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`,
      body,
      { accessToken }
    ),
};
