// Typed REAL-mode client for the helicopter (/helicopters) and eVTOL (/evtols) fleet APIs
// (backend/app/api/v1/airframes.py). Identity is the Asset; `detail` is the 1:1 airframe detail row.

import { apiRequest } from "@/lib/apiClient";

export interface AirframeResponse {
  id: string;
  organization_id: string;
  asset_type: string;
  registration: string | null;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  status: string;
  facility_id: string | null;
  detail: Record<string, string | number | null>;
}

export interface AirframeComponent {
  id: string;
  component_type: string;
  name: string;
  serial_number: string | null;
  status: string;
}

export interface AirframeUtilization {
  asset_id: string;
  total_flights: number;
  total_minutes: number;
  total_cycles: number;
}

export interface AirframeBattery {
  id: string;
  serial_number: string;
  manufacturer: string | null;
  capacity_mah: number | null;
  voltage: number | null;
  status: string;
}

export interface MaintenanceDue {
  requirement_id?: string;
  title?: string;
  name?: string;
  status?: string;
  due_status?: string;
  [k: string]: unknown;
}

export function airframesApi(basePath: string) {
  return {
    list: (accessToken: string) => apiRequest<AirframeResponse[]>(basePath, { accessToken }),
    create: (
      accessToken: string,
      payload: { registration: string; manufacturer?: string | null; model?: string | null; detail?: Record<string, unknown> }
    ) => apiRequest<AirframeResponse>(basePath, { method: "POST", body: payload, accessToken }),
    get: (accessToken: string, id: string) => apiRequest<AirframeResponse>(`${basePath}/${id}`, { accessToken }),
    update: (
      accessToken: string,
      id: string,
      payload: { status?: string; manufacturer?: string | null; model?: string | null; detail?: Record<string, unknown> }
    ) => apiRequest<AirframeResponse>(`${basePath}/${id}`, { method: "PATCH", body: payload, accessToken }),
    utilization: (accessToken: string, id: string) =>
      apiRequest<AirframeUtilization>(`${basePath}/${id}/utilization`, { accessToken }),
    components: (accessToken: string, id: string) =>
      apiRequest<AirframeComponent[]>(`${basePath}/${id}/components`, { accessToken }),
    addComponent: (accessToken: string, id: string, payload: { component_type: string; name: string; serial_number?: string | null }) =>
      apiRequest<AirframeComponent>(`${basePath}/${id}/components`, { method: "POST", body: payload, accessToken }),
    recordFlight: (accessToken: string, id: string, payload: { flown_at: string; duration_minutes: number; cycles: number }) =>
      apiRequest<unknown>(`${basePath}/${id}/flights`, { method: "POST", body: payload, accessToken }),
    maintenanceDue: (accessToken: string, id: string) =>
      apiRequest<MaintenanceDue[]>(`${basePath}/${id}/maintenance-due`, { accessToken }),
    applyHumsTemplate: (accessToken: string, id: string) =>
      apiRequest<{ created: string[]; skipped: string[] }>(`${basePath}/${id}/hums/apply-template`, { method: "POST", accessToken }),
    attachBattery: (accessToken: string, id: string, payload: { serial_number: string }) =>
      apiRequest<AirframeBattery>(`${basePath}/${id}/batteries`, { method: "POST", body: payload, accessToken }),
    batteries: (accessToken: string, id: string) =>
      apiRequest<AirframeBattery[]>(`${basePath}/${id}/batteries`, { accessToken }),
  };
}
