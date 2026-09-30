// Typed REAL-mode client for the per-asset telemetry read APIs
// (backend/app/api/v1/telemetry.py, Phase C). Thin: no derivation happens here — latest values,
// ages and states are computed by the backend from stored readings.

import { apiRequest } from "@/lib/apiClient";

export interface TelemetryStatus {
  asset_id: string;
  source_system: string | null;
  external_asset_id: string | null;
  telemetry_state: "ACTIVE" | "STALE" | "NO_TELEMETRY_RECORDED" | string;
  freshness_warning_threshold_days: number;
  freshness_critical_threshold_days: number;
  last_received_at: string | null;
  total_recent_events: number;
}

export interface LatestSensorReading {
  sensor_id: string;
  sensor_code: string;
  sensor_type: string;
  measurement_type: string;
  unit: string;
  value: number;
  data_quality: string;
  recorded_at: string;
  age_seconds: number;
  flight_id: string | null;
}

export interface LatestReadings {
  asset_id: string;
  as_of: string;
  sensor_count: number;
  sensors: LatestSensorReading[];
}

export interface TelemetryFlight {
  flight_id: string;
  flight_number: string | null;
  flown_at: string;
  duration_minutes: number;
  cycles: number;
  status: string;
}

export const telemetryApi = {
  status: (accessToken: string, assetId: string) =>
    apiRequest<TelemetryStatus>(`/telemetry/assets/${assetId}/status`, { accessToken }),
  latest: (accessToken: string, assetId: string) =>
    apiRequest<LatestReadings>(`/telemetry/assets/${assetId}/latest`, { accessToken }),
  flights: (accessToken: string, assetId: string) =>
    apiRequest<TelemetryFlight[]>(`/telemetry/assets/${assetId}/flights?limit=10`, { accessToken }),
};
