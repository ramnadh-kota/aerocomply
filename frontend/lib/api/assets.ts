import { apiRequest } from "@/lib/apiClient";

export interface AssetResponse {
  id: string;
  organization_id: string;
  asset_type: string;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  registration: string | null;
  status: string;
  acquired_at: string | null;
  retired_at: string | null;
  facility_id?: string | null;
  created_at: string;
}

export interface AssetCreateRequest {
  asset_type: string;
  registration: string;
  manufacturer?: string | null;
  model?: string | null;
  serial_number?: string | null;
  facility_id?: string | null;
  status?: string;
}

export interface AssetUpdateRequest {
  manufacturer?: string | null;
  model?: string | null;
  serial_number?: string | null;
  facility_id?: string | null;
  status?: string | null;
}

export interface AssetComponentResponse {
  id: string;
  organization_id: string;
  asset_id: string | null;
  component_type: string;
  name: string;
  serial_number: string | null;
  manufacturer: string | null;
  model: string | null;
  status: string;
  installed_at: string | null;
  created_at: string;
}

export interface AssetInstallComponentRequest {
  component_type: string;
  name: string;
  serial_number?: string | null;
  manufacturer?: string | null;
  model?: string | null;
  notes?: string | null;
}

export interface AssetConfigurationSlotResponse {
  slot_name: string;
  component_type: string;
  is_occupied: boolean;
  component: AssetComponentResponse | null;
}

export interface AssetConfigurationResponse {
  asset_id: string;
  asset_type: string;
  airframe_spec: Record<string, any>;
  slots: AssetConfigurationSlotResponse[];
  total_components_installed: number;
}

export interface UsageMetricItem {
  metric_key: string;
  metric_label: string;
  value: number;
  unit: string;
  source: string;
  is_metered: boolean;
}

export interface AssetUtilizationResponse {
  asset_id: string;
  asset_type: string;
  total_flight_hours: number;
  total_minutes: number;
  total_cycles: number;
  total_flights: number;
  total_landings: number;
  metrics: UsageMetricItem[];
}

export interface AssetFlightResponse {
  id: string;
  organization_id: string;
  asset_id: string;
  mission_id: string | null;
  flown_at: string;
  duration_minutes: number;
  cycles: number;
  pilot_user_id: string | null;
  notes: string | null;
  created_at: string;
}

export interface AssetFlightCreateRequest {
  flown_at: string;
  duration_minutes: number;
  cycles?: number;
  pilot_user_id?: string | null;
  mission_id?: string | null;
  notes?: string | null;
}

export interface AssetOperationsResponse {
  asset_id: string;
  utilization: AssetUtilizationResponse;
  recent_flights: AssetFlightResponse[];
  active_missions: Record<string, any>[];
}

export interface AssetMaintenanceResponse {
  asset_id: string;
  due_items: Record<string, any>[];
  accomplishments: Record<string, any>[];
  open_work_orders: Record<string, any>[];
  has_overdue: boolean;
}

export interface AssetInspectionsResponse {
  asset_id: string;
  inspections: Record<string, any>[];
  total: number;
  completed: number;
  pending: number;
}

export interface AssetEvidenceResponse {
  asset_id: string;
  evidence_items: Record<string, any>[];
  total: number;
  accepted_count: number;
  pending_count: number;
}

export interface AssetFindingsResponse {
  asset_id: string;
  findings: Record<string, any>[];
  total: number;
  open_count: number;
  closed_count: number;
}

export interface AssetComplianceResponse {
  asset_id: string;
  assessments: Record<string, any>[];
  overall_status: string;
  compliant_count: number;
  non_compliant_count: number;
}

export interface ReadinessDimension {
  dimension: string;
  status: string;
  summary: string;
  blockers: string[];
}

export interface AssetReadinessResponse {
  asset_id: string;
  overall_status: string;
  dimensions: ReadinessDimension[];
  evaluated_at: string;
  disclaimer: string;
}

export interface AssetHistoryEventResponse {
  event_id: string;
  event_type: string;
  occurred_at: string;
  title: string;
  description: string;
  actor: string | null;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, any>;
}

export interface AssetHistoryResponse {
  asset_id: string;
  events: AssetHistoryEventResponse[];
  total: number;
}

export interface AssetDomainContextResponse {
  identity: AssetResponse;
  operational_status: string;
  lifecycle_status: string;
  readiness: AssetReadinessResponse;
  configuration: AssetConfigurationResponse;
  utilization: AssetUtilizationResponse;
  compliance: AssetComplianceResponse;
  open_work_orders_count: number;
  open_findings_count: number;
  overdue_maintenance_count: number;
  last_flight_at: string | null;
}

export const assetsApi = {
  listAssets: (
    accessToken: string,
    params?: { asset_type?: string; status?: string; search?: string }
  ) => {
    const query = new URLSearchParams();
    if (params?.asset_type) query.set("asset_type", params.asset_type);
    if (params?.status) query.set("status", params.status);
    if (params?.search) query.set("search", params.search);
    const qs = query.toString();
    return apiRequest<AssetResponse[]>(`/assets${qs ? `?${qs}` : ""}`, {
      accessToken,
    });
  },

  getAsset: (accessToken: string, assetId: string) =>
    apiRequest<AssetResponse>(`/assets/${assetId}`, { accessToken }),

  createAsset: (accessToken: string, data: AssetCreateRequest) =>
    apiRequest<AssetResponse>("/assets", {
      accessToken,
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateAsset: (
    accessToken: string,
    assetId: string,
    data: AssetUpdateRequest
  ) =>
    apiRequest<AssetResponse>(`/assets/${assetId}`, {
      accessToken,
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getConfiguration: (accessToken: string, assetId: string) =>
    apiRequest<AssetConfigurationResponse>(`/assets/${assetId}/configuration`, {
      accessToken,
    }),

  getComponents: (accessToken: string, assetId: string) =>
    apiRequest<AssetComponentResponse[]>(`/assets/${assetId}/components`, {
      accessToken,
    }),

  installComponent: (
    accessToken: string,
    assetId: string,
    data: AssetInstallComponentRequest
  ) =>
    apiRequest<AssetComponentResponse>(`/assets/${assetId}/components`, {
      accessToken,
      method: "POST",
      body: JSON.stringify(data),
    }),

  removeComponent: (accessToken: string, assetId: string, componentId: string) =>
    apiRequest<AssetComponentResponse>(
      `/assets/${assetId}/components/${componentId}`,
      {
        accessToken,
        method: "DELETE",
      }
    ),

  getOperations: (accessToken: string, assetId: string) =>
    apiRequest<AssetOperationsResponse>(`/assets/${assetId}/operations`, {
      accessToken,
    }),

  recordFlight: (
    accessToken: string,
    assetId: string,
    data: AssetFlightCreateRequest
  ) =>
    apiRequest<AssetFlightResponse>(`/assets/${assetId}/flights`, {
      accessToken,
      method: "POST",
      body: JSON.stringify(data),
    }),

  getUtilization: (accessToken: string, assetId: string) =>
    apiRequest<AssetUtilizationResponse>(`/assets/${assetId}/utilization`, {
      accessToken,
    }),

  getMaintenance: (accessToken: string, assetId: string) =>
    apiRequest<AssetMaintenanceResponse>(`/assets/${assetId}/maintenance`, {
      accessToken,
    }),

  getInspections: (accessToken: string, assetId: string) =>
    apiRequest<AssetInspectionsResponse>(`/assets/${assetId}/inspections`, {
      accessToken,
    }),

  getEvidence: (accessToken: string, assetId: string) =>
    apiRequest<AssetEvidenceResponse>(`/assets/${assetId}/evidence`, {
      accessToken,
    }),

  getFindings: (accessToken: string, assetId: string) =>
    apiRequest<AssetFindingsResponse>(`/assets/${assetId}/findings`, {
      accessToken,
    }),

  getCompliance: (accessToken: string, assetId: string) =>
    apiRequest<AssetComplianceResponse>(`/assets/${assetId}/compliance`, {
      accessToken,
    }),

  getReadiness: (accessToken: string, assetId: string) =>
    apiRequest<AssetReadinessResponse>(`/assets/${assetId}/readiness`, {
      accessToken,
    }),

  getHistory: (accessToken: string, assetId: string) =>
    apiRequest<AssetHistoryResponse>(`/assets/${assetId}/history`, {
      accessToken,
    }),

  getContext: (accessToken: string, assetId: string) =>
    apiRequest<AssetDomainContextResponse>(`/assets/${assetId}/context`, {
      accessToken,
    }),
};
