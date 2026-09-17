// Typed REAL-mode client for the Drone Operations vertical slice
// (backend/app/api/v1/drones.py). Drone identity is the existing Asset
// (asset_type=DRONE) -- no separate drone identity is introduced here
// either. Requires DRONE_READ/DRONE_WRITE on the backend.

import { apiRequest } from "@/lib/apiClient";

export interface DroneResponse {
  id: string;
  organization_id: string;
  asset_type: string;
  registration: string | null;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  status: string;
  facility_id: string | null;
  created_at: string;
}

export interface BatteryResponse {
  id: string;
  organization_id: string;
  asset_id: string | null;
  serial_number: string;
  manufacturer: string | null;
  model: string | null;
  capacity_mah: number | null;
  voltage: number | null;
  cycle_count: number;
  health_percent: number | null;
  status: "GOOD" | "MONITOR" | "SERVICE_DUE" | "CRITICAL" | "RETIRED";
  installed_at: string | null;
  notes: string | null;
  created_at: string;
}

export interface ComponentResponse {
  id: string;
  organization_id: string;
  asset_id: string | null;
  component_type: string;
  name: string;
  serial_number: string | null;
  manufacturer: string | null;
  model: string | null;
  status: string;
  created_at: string;
}

export interface FlightResponse {
  id: string;
  organization_id: string;
  asset_id: string;
  flown_at: string;
  duration_minutes: number;
  cycles: number;
  pilot_user_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface UtilizationResponse {
  asset_id: string;
  total_flights: number;
  total_minutes: number;
  total_cycles: number;
}

export interface DeploymentReadinessResponse {
  asset_id: string;
  status: "READY" | "BLOCKED";
  blockers: string[];
}

export const dronesApi = {
  listDrones: (accessToken: string) => apiRequest<DroneResponse[]>("/drones", { accessToken }),

  createDrone: (
    accessToken: string,
    payload: { registration: string; manufacturer?: string | null; model?: string | null; facility_id?: string | null }
  ) => apiRequest<DroneResponse>("/drones", { method: "POST", body: payload, accessToken }),

  getDrone: (accessToken: string, assetId: string) =>
    apiRequest<DroneResponse>(`/drones/${assetId}`, { accessToken }),

  updateDrone: (
    accessToken: string,
    assetId: string,
    payload: { status?: string; manufacturer?: string | null; model?: string | null; facility_id?: string | null }
  ) => apiRequest<DroneResponse>(`/drones/${assetId}`, { method: "PATCH", body: payload, accessToken }),

  listBatteries: (accessToken: string, assetId: string) =>
    apiRequest<BatteryResponse[]>(`/drones/${assetId}/batteries`, { accessToken }),

  attachBattery: (
    accessToken: string,
    assetId: string,
    payload: { serial_number: string; manufacturer?: string | null; capacity_mah?: number | null }
  ) =>
    apiRequest<BatteryResponse>(`/drones/${assetId}/batteries`, {
      method: "POST",
      body: payload,
      accessToken,
    }),

  updateBattery: (accessToken: string, batteryId: string, payload: { status?: string; health_percent?: number }) =>
    apiRequest<BatteryResponse>(`/batteries/${batteryId}`, { method: "PATCH", body: payload, accessToken }),

  listComponents: (accessToken: string, assetId: string) =>
    apiRequest<ComponentResponse[]>(`/drones/${assetId}/components`, { accessToken }),

  attachComponent: (
    accessToken: string,
    assetId: string,
    payload: { component_type: string; name: string; serial_number?: string | null }
  ) =>
    apiRequest<ComponentResponse>(`/drones/${assetId}/components`, {
      method: "POST",
      body: payload,
      accessToken,
    }),

  listFlights: (accessToken: string, assetId: string) =>
    apiRequest<FlightResponse[]>(`/drones/${assetId}/flights`, { accessToken }),

  recordFlight: (
    accessToken: string,
    assetId: string,
    payload: { flown_at: string; duration_minutes: number; cycles?: number; notes?: string | null }
  ) =>
    apiRequest<FlightResponse>(`/drones/${assetId}/flights`, {
      method: "POST",
      body: payload,
      accessToken,
    }),

  getUtilization: (accessToken: string, assetId: string) =>
    apiRequest<UtilizationResponse>(`/drones/${assetId}/utilization`, { accessToken }),

  getDeploymentReadiness: (accessToken: string, assetId: string) =>
    apiRequest<DeploymentReadinessResponse>(`/drones/${assetId}/deployment-readiness`, { accessToken }),
};
