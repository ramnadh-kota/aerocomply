// Typed client for the Live Drone Operations API (backend/app/api/v1/live.py).
// Read-only snapshots + real-time fleet state. Gated by DRONE_READ and flight_telemetry.

import { apiRequest } from "@/lib/apiClient";

export interface FreshnessV1 {
  state: "FRESH" | "STALE" | "LOST" | "NO_DATA";
  age_seconds: number | null;
  stale_after_seconds: number;
  lost_after_seconds: number;
  evaluated_at: string;
}

export interface LiveIdentityV1 {
  asset_id: string;
  device_id: string | null;
  data_source_id: string | null;
  source_system: string | null;
  source_asset_id: string | null;
}

export interface PositionV1 {
  observed_at: string | null;
  lat: number | null;
  lon: number | null;
  alt_msl_m: number | null;
  alt_rel_m: number | null;
  gps_fix_type: number | null;
  gps_fix: string | null;
  satellites: number | null;
  hdop: number | null;
  reference: string;
}

export interface MotionV1 {
  observed_at: string | null;
  ground_speed_mps: number | null;
  air_speed_mps: number | null;
  climb_rate_mps: number | null;
  heading_deg: number | null;
}

export interface AttitudeV1 {
  observed_at: string | null;
  roll_deg: number | null;
  pitch_deg: number | null;
  yaw_deg: number | null;
}

export interface BatteryV1 {
  observed_at: string | null;
  voltage_v: number | null;
  current_a: number | null;
  remaining_pct: number | null;
  temperature_c: number | null;
}

export interface ModeV1 {
  observed_at: string | null;
  armed: boolean | null;
  flight_mode: string | null;
  custom_mode: number | null;
  autopilot: string | null;
}

export interface LiveStateV1 {
  schema: string;
  identity: LiveIdentityV1;
  state_version: number;
  observed_at: string | null;
  received_at: string | null;
  freshness: FreshnessV1;
  connectivity: "ONLINE" | "DEGRADED" | "OFFLINE" | "REVOKED" | "UNKNOWN";
  position: PositionV1;
  motion: MotionV1;
  attitude: AttitudeV1;
  battery: BatteryV1;
  mode: ModeV1;
  mission: Record<string, any>;
  status_texts: Array<{ severity: number; severity_name: string; text: string; observed_at: string }>;
  provenance: Record<string, any>;
}

export interface LiveFleetResponse {
  cursor: string;
  drones: LiveStateV1[];
  alerts: Array<Record<string, any>>;
}

export const liveApi = {
  getFleet: (accessToken: string) =>
    apiRequest<LiveFleetResponse>("/live/fleet", { accessToken }),
  getDroneState: (accessToken: string, assetId: string) =>
    apiRequest<LiveStateV1>(`/live/drones/${assetId}`, { accessToken }),
};
