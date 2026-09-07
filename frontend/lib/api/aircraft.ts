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

export const aircraftApi = {
  list: (accessToken: string) => apiRequest<BackendAircraft[]>("/aircraft", { accessToken }),

  get: (accessToken: string, aircraftId: string) =>
    apiRequest<BackendAircraft>(`/aircraft/${aircraftId}`, { accessToken }),
};
