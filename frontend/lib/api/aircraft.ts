// Typed REAL-mode client for the backend Aircraft endpoints
// (backend/app/api/v1/aircraft.py). organization_id is never sent by the
// client — the backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendAircraft {
  id: string;
  organization_id: string;
  registration: string;
  msn: string;
  aircraft_type: string;
  status: string;
  created_at: string;
}

export interface AircraftCreateRequest {
  registration: string;
  msn: string;
  aircraft_type: string;
  status?: string;
  manufacturer?: string | null;
}

export interface AircraftUpdateRequest {
  manufacturer?: string | null;
  msn?: string;
  aircraft_type?: string;
  status?: string;
}

export const aircraftApi = {
  list: (accessToken: string) => apiRequest<BackendAircraft[]>("/aircraft", { accessToken }),

  get: (accessToken: string, aircraftId: string) =>
    apiRequest<BackendAircraft>(`/aircraft/${aircraftId}`, { accessToken }),

  create: (accessToken: string, data: AircraftCreateRequest) =>
    apiRequest<BackendAircraft>("/aircraft", {
      accessToken,
      method: "POST",
      body: data,
    }),

  update: (accessToken: string, aircraftId: string, data: AircraftUpdateRequest) =>
    apiRequest<BackendAircraft>(`/aircraft/${aircraftId}`, {
      accessToken,
      method: "PATCH",
      body: data,
    }),
};
