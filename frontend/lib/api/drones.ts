// Typed REAL-mode client for the Drone Operations vertical slice
// (backend/app/api/v1/drones.py). Drone identity is the existing Asset
// (asset_type=DRONE) -- no separate drone identity is introduced here
// either. Requires DRONE_READ/DRONE_WRITE on the backend.

import { apiRequest, type CurrentUser } from "@/lib/apiClient";

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

// M17.3B: paginated flight-history envelope (backend/app/schemas/drone_ops.py
// FlightListResponse), same {items, total, limit, offset} shape as the
// M17.2B lifecycle-history endpoints below.
export interface FlightListResponse {
  items: FlightResponse[];
  total: number;
  limit: number;
  offset: number;
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

// M17.2C: lifecycle history types, matching backend/app/schemas/drone_ops.py
// exactly (added in M17.2B: backend/app/api/v1/drones.py). Battery.asset_id
// / Component.asset_id above remain the ONLY current-state source of truth
// -- these are purely historical/read-only records, never used to derive
// current assignment.

export interface BatteryInstallationResponse {
  id: string;
  organization_id: string;
  battery_id: string;
  asset_id: string;
  installed_at: string;
  removed_at: string | null;
  installed_by: string | null;
  removed_by: string | null;
}

export interface BatteryInstallationListResponse {
  items: BatteryInstallationResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface ComponentInstallationResponse {
  id: string;
  organization_id: string;
  component_id: string;
  asset_id: string;
  installed_at: string;
  removed_at: string | null;
  installed_by: string | null;
  removed_by: string | null;
}

export interface ComponentInstallationListResponse {
  items: ComponentInstallationResponse[];
  total: number;
  limit: number;
  offset: number;
}

// Exactly the four values app/services/installation_service.py's
// LifecycleEventType emits -- never invent an additional event value here.
export type LifecycleEventType =
  | "BATTERY_INSTALLATION"
  | "BATTERY_REMOVAL"
  | "COMPONENT_INSTALLATION"
  | "COMPONENT_REMOVAL";

export interface AssetLifecycleEventResponse {
  event_type: LifecycleEventType;
  occurred_at: string;
  asset_id: string;
  installation_id: string;
  battery_id: string | null;
  component_id: string | null;
  actor_user_id: string | null;
}

export interface AssetLifecycleHistoryResponse {
  items: AssetLifecycleEventResponse[];
  total: number;
  limit: number;
  offset: number;
}

interface LifecyclePageParams {
  limit?: number;
  offset?: number;
}

function lifecycleQuery(params?: LifecyclePageParams): string {
  if (!params) return "";
  const parts: string[] = [];
  if (params.limit !== undefined) parts.push(`limit=${params.limit}`);
  if (params.offset !== undefined) parts.push(`offset=${params.offset}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

// M17.4A/B + M17.5A/B: usage-based maintenance types, matching
// backend/app/schemas/maintenance_requirement.py exactly. Reuses the
// existing MaintenanceRequirement/Applicability/Accomplishment
// architecture (originally aircraft-only) extended for Drone/Asset and,
// as of M17.5, Battery/Component.

export type MaintenanceIntervalType =
  | "FLIGHT_HOURS"
  | "FLIGHT_CYCLES"
  | "CALENDAR"
  | "BATTERY_CYCLES"
  | "COMPONENT_HOURS"
  | "COMPONENT_CYCLES";

export interface MaintenanceRequirementResponse {
  id: string;
  organization_id: string;
  description: string;
  ata_chapter: string;
  interval_type: MaintenanceIntervalType;
  fh_interval: number | null;
  fc_interval: number | null;
  calendar_interval_days: number | null;
  task_reference: string | null;
}

export interface MaintenanceDueItem {
  requirement: MaintenanceRequirementResponse;
  aircraft_id: string | null;
  asset_id: string | null;
  battery_id: string | null;
  component_id: string | null;
  last_accomplished_at: string | null;
  due_status: "OVERDUE" | "DUE_SOON" | "NOT_DUE" | "UNKNOWN";
  due_date: string | null;
  reason: string;
  // current_usage = usage SINCE last accomplishment (what due_status is
  // computed from). lifetime_usage (M17.5B) = total usage ever, never
  // reset by an accomplishment. Deliberately different numbers -- see
  // backend/app/services/maintenance_service.py's module docstring.
  current_usage: number | null;
  remaining_usage: number | null;
  lifetime_usage: number | null;
}

export interface MaintenanceAccomplishmentResponse {
  id: string;
  requirement_id: string;
  aircraft_id: string | null;
  asset_id: string | null;
  battery_id: string | null;
  component_id: string | null;
  accomplished_at: string;
  work_order_id: string | null;
  notes: string | null;
}

// --- Permission UX hint ---
//
// Mirrors the DRONE_WRITE grant set in backend/app/core/permissions.py's
// ROLE_PERMISSIONS (ORG_ADMIN, CAMO_MANAGER, plus SUPER_ADMIN which holds
// every permission) -- same "UX hint only, backend remains authoritative"
// convention as lib/api/evidenceFiles.ts's canWriteEvidenceFiles. This
// only hides/disables the Record Flight control for a user who would get
// a 403 anyway; it changes nothing about what the backend actually
// allows -- a user who bypasses this still hits the real
// require_permission(Permission.DRONE_WRITE) check server-side.
const DRONE_WRITE_ROLES = new Set(["SUPER_ADMIN", "ORG_ADMIN", "CAMO_MANAGER"]);

export function canRecordFlight(user: CurrentUser | null): boolean {
  if (!user) return false;
  return user.roles.some((role) => DRONE_WRITE_ROLES.has(role));
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

  // M17.3B: paginated -- was list[FlightResponse] (unbounded). Uses the
  // same limit/offset query-string convention as the lifecycle-history
  // calls below.
  listFlights: (accessToken: string, assetId: string, params?: LifecyclePageParams) =>
    apiRequest<FlightListResponse>(`/drones/${assetId}/flights${lifecycleQuery(params)}`, {
      accessToken,
    }),

  getFlight: (accessToken: string, flightId: string) =>
    apiRequest<FlightResponse>(`/flights/${flightId}`, { accessToken }),

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

  // M17.2C: lifecycle read APIs (backend/app/api/v1/drones.py, added M17.2B).
  // organization_id is never sent by the client -- it is derived
  // server-side from the bearer token, same as every other call here.

  getBattery: (accessToken: string, batteryId: string) =>
    apiRequest<BatteryResponse>(`/batteries/${batteryId}`, { accessToken }),

  getBatteryHistory: (accessToken: string, batteryId: string, params?: LifecyclePageParams) =>
    apiRequest<BatteryInstallationListResponse>(
      `/batteries/${batteryId}/history${lifecycleQuery(params)}`,
      { accessToken }
    ),

  getComponent: (accessToken: string, componentId: string) =>
    apiRequest<ComponentResponse>(`/components/${componentId}`, { accessToken }),

  getComponentHistory: (accessToken: string, componentId: string, params?: LifecyclePageParams) =>
    apiRequest<ComponentInstallationListResponse>(
      `/components/${componentId}/history${lifecycleQuery(params)}`,
      { accessToken }
    ),

  getAssetLifecycleHistory: (accessToken: string, assetId: string, params?: LifecyclePageParams) =>
    apiRequest<AssetLifecycleHistoryResponse>(
      `/drones/${assetId}/lifecycle-history${lifecycleQuery(params)}`,
      { accessToken }
    ),

  // M17.4A/B: usage-based maintenance for a drone.

  getMaintenanceDue: (accessToken: string, assetId: string) =>
    apiRequest<MaintenanceDueItem[]>(`/drones/${assetId}/maintenance-due`, { accessToken }),

  listMaintenanceRequirements: (accessToken: string) =>
    apiRequest<MaintenanceRequirementResponse[]>("/maintenance-requirements", { accessToken }),

  createMaintenanceRequirement: (
    accessToken: string,
    payload: {
      description: string;
      ata_chapter: string;
      interval_type: MaintenanceIntervalType;
      fh_interval?: number | null;
      fc_interval?: number | null;
      calendar_interval_days?: number | null;
    }
  ) =>
    apiRequest<MaintenanceRequirementResponse>("/maintenance-requirements", {
      method: "POST",
      body: payload,
      accessToken,
    }),

  addMaintenanceApplicability: (accessToken: string, assetId: string, requirementId: string) =>
    apiRequest<MaintenanceRequirementResponse>(
      `/drones/${assetId}/maintenance-requirements/${requirementId}/applicability`,
      { method: "POST", accessToken }
    ),

  recordMaintenanceAccomplishment: (
    accessToken: string,
    assetId: string,
    requirementId: string,
    payload: { accomplished_at: string; notes?: string | null }
  ) =>
    apiRequest<MaintenanceAccomplishmentResponse>(
      `/drones/${assetId}/maintenance-requirements/${requirementId}/accomplishments`,
      { method: "POST", body: payload, accessToken }
    ),

  // M17.5A/B: usage-based maintenance for a serialized Battery/Component --
  // same request/response shapes as the asset(Drone) methods above, just a
  // different path prefix.

  getBatteryMaintenanceDue: (accessToken: string, batteryId: string) =>
    apiRequest<MaintenanceDueItem[]>(`/batteries/${batteryId}/maintenance-due`, { accessToken }),

  addBatteryMaintenanceApplicability: (
    accessToken: string,
    batteryId: string,
    requirementId: string
  ) =>
    apiRequest<MaintenanceRequirementResponse>(
      `/batteries/${batteryId}/maintenance-requirements/${requirementId}/applicability`,
      { method: "POST", accessToken }
    ),

  recordBatteryMaintenanceAccomplishment: (
    accessToken: string,
    batteryId: string,
    requirementId: string,
    payload: { accomplished_at: string; notes?: string | null }
  ) =>
    apiRequest<MaintenanceAccomplishmentResponse>(
      `/batteries/${batteryId}/maintenance-requirements/${requirementId}/accomplishments`,
      { method: "POST", body: payload, accessToken }
    ),

  getComponentMaintenanceDue: (accessToken: string, componentId: string) =>
    apiRequest<MaintenanceDueItem[]>(`/components/${componentId}/maintenance-due`, {
      accessToken,
    }),

  addComponentMaintenanceApplicability: (
    accessToken: string,
    componentId: string,
    requirementId: string
  ) =>
    apiRequest<MaintenanceRequirementResponse>(
      `/components/${componentId}/maintenance-requirements/${requirementId}/applicability`,
      { method: "POST", accessToken }
    ),

  recordComponentMaintenanceAccomplishment: (
    accessToken: string,
    componentId: string,
    requirementId: string,
    payload: { accomplished_at: string; notes?: string | null }
  ) =>
    apiRequest<MaintenanceAccomplishmentResponse>(
      `/components/${componentId}/maintenance-requirements/${requirementId}/accomplishments`,
      { method: "POST", body: payload, accessToken }
    ),
};
