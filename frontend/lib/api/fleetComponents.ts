// Typed REAL-mode client for the organization-wide component register (backend/app/api/v1/fleet_components.py).
import { apiRequest } from "@/lib/apiClient";

export interface FleetComponent {
  id: string;
  asset_id: string | null;
  asset_registration: string | null;
  asset_type: string | null;
  component_type: string;
  name: string;
  serial_number: string | null;
  manufacturer: string | null;
  model: string | null;
  status: string;
  created_at: string | null;
}

export interface FleetComponentList {
  items: FleetComponent[];
  total: number;
  limit: number;
  offset: number;
}

export const fleetComponentsApi = {
  list: (accessToken: string, params: { component_type?: string; asset_id?: string; status?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
    const qs = q.toString();
    return apiRequest<FleetComponentList>(`/fleet/components${qs ? `?${qs}` : ""}`, { accessToken });
  },
  get: (accessToken: string, id: string) => apiRequest<FleetComponent>(`/fleet/components/${id}`, { accessToken }),
};
