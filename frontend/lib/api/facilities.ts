// Typed REAL-mode client for tenant Facilities administration
// (backend/app/api/v1/facilities.py). Requires FACILITY_READ/FACILITY_WRITE
// on the backend — the server always derives organization scope from the
// signed-in session, never from anything sent by this client.

import { apiRequest } from "@/lib/apiClient";

export const FACILITY_TYPES = [
  "HANGAR",
  "WORKSHOP",
  "WAREHOUSE",
  "STATION",
  "OFFICE",
  "STORE",
  "OTHER",
] as const;
export type FacilityType = (typeof FACILITY_TYPES)[number];

export interface FacilityResponse {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  facility_type: string;
  status: "ACTIVE" | "INACTIVE";
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface FacilityCreateRequest {
  code: string;
  name: string;
  facility_type: string;
  description?: string | null;
}

export interface FacilityUpdateRequest {
  name?: string;
  facility_type?: string;
  status?: "ACTIVE" | "INACTIVE";
  description?: string | null;
}

export const facilitiesApi = {
  listFacilities: (accessToken: string) =>
    apiRequest<FacilityResponse[]>("/facilities", { accessToken }),

  createFacility: (accessToken: string, payload: FacilityCreateRequest) =>
    apiRequest<FacilityResponse>("/facilities", { method: "POST", body: payload, accessToken }),

  getFacility: (accessToken: string, id: string) =>
    apiRequest<FacilityResponse>(`/facilities/${id}`, { accessToken }),

  updateFacility: (accessToken: string, id: string, payload: FacilityUpdateRequest) =>
    apiRequest<FacilityResponse>(`/facilities/${id}`, {
      method: "PATCH",
      body: payload,
      accessToken,
    }),
};
