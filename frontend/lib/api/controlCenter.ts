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

export type AssetOperationalState =
  | "AVAILABLE"
  | "IN_MISSION"
  | "UNDER_INSPECTION"
  | "MAINTENANCE"
  | "GROUNDED"
  | "AOG"
  | "INACTIVE"
  | "RETIRED";

export interface ControlCenterFleetHealth {
  total_assets: number;
  ready_count: number;
  restricted_count: number;
  maintenance_due_count: number;
  grounded_count: number;
  available_count: number;
  in_mission_count: number;
  unknown_count: number;
  asset_class_counts: Record<string, number>;
}

export interface ControlCenterOperationalActivity {
  flights_today: number;
  flights_this_week: number;
  total_flight_hours: number;
  total_cycles: number;
  total_flights: number;
  active_missions: number;
}

export interface ControlCenterAttentionItem {
  id: string;
  asset_id: string | null;
  registration: string | null;
  asset_type: string | null;
  priority: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
  category: "INSPECTION" | "MAINTENANCE" | "COMPLIANCE" | "FINDING" | "MATERIAL" | "BATTERY";
  title: string;
  reason: string;
  blocking_condition: string | null;
  recommended_action: string | null;
  link_href: string | null;
}

export interface ControlCenterDailyBrief {
  date_str: string;
  total_assets: number;
  ready_assets: number;
  attention_required_count: number;
  restricted_assets: number;
  maintenance_due_count: number;
  pending_inspections_count: number;
  open_findings_count: number;
  summary_headline: string;
  key_bullet_points: string[];
  generated_at: string;
}

export interface ControlCenterFleetOperationRow {
  asset_id: string;
  registration: string | null;
  asset_type: string;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  lifecycle_status: string;
  operational_state: AssetOperationalState;
  readiness_state: "READY" | "BLOCKED" | "UNKNOWN";
  risk_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
  priority_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
  total_flight_hours: number;
  total_cycles: number;
  last_flight_at: string | null;
  open_work_orders: number;
  open_findings: number;
  active_blocker_count: number;
  next_action: string | null;
}

export interface OperationalTimelineEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  title: string;
  description: string | null;
  actor: string | null;
  entity_type: string;
  entity_id: string;
  asset_id: string | null;
  asset_registration: string | null;
  asset_type: string | null;
  metadata: Record<string, any>;
}

export interface ControlCenterSummary {
  total_aircraft: number;
  operational: number;
  under_maintenance: number;
  aog: number;
  open_work_orders_total: number;
  open_deferred_items_total: number;
  open_part_shortages_total: number;
  total_assets: number;
  operational_states: Partial<Record<AssetOperationalState, number>>;
  fleet_health?: ControlCenterFleetHealth | null;
  operational_activity?: ControlCenterOperationalActivity | null;
  attention_items?: ControlCenterAttentionItem[];
  daily_brief?: ControlCenterDailyBrief | null;
  readiness_distribution?: Record<string, number>;
  compliance_distribution?: Record<string, number>;
}

export const controlCenterApi = {
  getSummary: (accessToken: string) =>
    apiRequest<ControlCenterSummary>("/control-center/summary", { accessToken }),
  getFleet: (accessToken: string) =>
    apiRequest<ControlCenterAircraftRow[]>("/control-center/fleet", { accessToken }),
  getFleetOperations: (accessToken: string) =>
    apiRequest<ControlCenterFleetOperationRow[]>("/control-center/fleet-operations", { accessToken }),
  getTimeline: (
    accessToken: string,
    params?: { asset_id?: string; event_type?: string; limit?: number }
  ) => {
    const sp = new URLSearchParams();
    if (params?.asset_id) sp.set("asset_id", params.asset_id);
    if (params?.event_type) sp.set("event_type", params.event_type);
    if (params?.limit) sp.set("limit", String(params.limit));
    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return apiRequest<OperationalTimelineEvent[]>(`/control-center/timeline${qs}`, { accessToken });
  },
};
