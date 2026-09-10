// Typed REAL-mode client for the backend MRO Control Center endpoints
// (backend/app/api/v1/control_center.py). organization_id is never sent —
// the backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface ControlCenterAircraftRow {
  aircraft_id: string;
  registration: string;
  operational_status: "OPERATIONAL" | "UNDER_MAINTENANCE" | "AOG";
  open_work_orders: number;
  open_deferred_items: number;
  open_part_shortages: number;
  active_aog_event_id: string | null;
}

export interface ControlCenterSummary {
  total_aircraft: number;
  operational: number;
  under_maintenance: number;
  aog: number;
  open_work_orders_total: number;
  open_deferred_items_total: number;
  open_part_shortages_total: number;
}

export const controlCenterApi = {
  getSummary: (accessToken: string) =>
    apiRequest<ControlCenterSummary>("/control-center/summary", { accessToken }),
  getFleet: (accessToken: string) =>
    apiRequest<ControlCenterAircraftRow[]>("/control-center/fleet", { accessToken }),
};
