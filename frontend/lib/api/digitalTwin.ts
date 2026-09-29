// H6: Digital Asset & Component Twin — typed client for the read-only
// aggregation API (backend/app/api/v1/digital_twin.py). Every field here is
// populated by the backend calling an EXISTING service (asset_service,
// hums_service, readiness_intelligence_service, ...) -- this client never
// re-derives health/diagnosis/RUL/compliance/readiness, it only renders
// what those systems already concluded.

import { apiRequest } from "@/lib/apiClient";
import type { HUMSAssetHealthIntelligence, HUMSDiagnosticCandidate, HUMSPrognosticRecord } from "@/lib/api/hums";

export interface DigitalTwinIdentity {
  asset_id: string;
  asset_type: string;
  registration: string | null;
  serial_number: string | null;
  manufacturer: string | null;
  model: string | null;
  status: string;
}

export interface DigitalTwinMaintenanceState {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  open_work_order_count: number;
  open_finding_count: number;
  last_accomplishment_at: string | null;
}

export interface DigitalTwinComplianceState {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  assessment_count: number;
  summary: Record<string, unknown>;
}

export interface DigitalTwinReadinessState {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  readiness_state: string | null;
  blocker_count: number;
  blockers: string[];
}

export interface DigitalTwinAssetSnapshot {
  identity: DigitalTwinIdentity;
  configuration: { asset_id: string; asset_type: string; airframe_spec: Record<string, unknown>; slots: unknown[]; total_components_installed: number };
  usage: { asset_id: string; asset_type: string; total_flight_hours: number; total_minutes: number; total_cycles: number; total_flights: number; total_landings: number };
  health: HUMSAssetHealthIntelligence | null;
  diagnostics: HUMSDiagnosticCandidate[];
  prognostics: HUMSPrognosticRecord[];
  maintenance: DigitalTwinMaintenanceState;
  compliance: DigitalTwinComplianceState;
  readiness: DigitalTwinReadinessState;
  generated_at: string;
}

export interface DigitalTwinComponentNode {
  component: {
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
  };
  health_state: string | null;
  diagnostic_count: number;
  active_prognostic_status: string | null;
}

export interface DigitalTwinComponentSnapshot {
  component: DigitalTwinComponentNode["component"];
  current_asset_id: string | null;
  installed_at: string | null;
  genealogy_entry_count: number;
  health: Record<string, unknown> | null;
  diagnostics: HUMSDiagnosticCandidate[];
  prognostics: HUMSPrognosticRecord[];
  generated_at: string;
}

export interface DigitalTwinGenealogyEntry {
  installation_id: string;
  asset_id: string;
  asset_registration: string | null;
  installed_at: string;
  removed_at: string | null;
  is_current: boolean;
}

export interface DigitalTwinTimelineEvent {
  occurred_at: string;
  event_type: string;
  summary: string;
  source_type: string;
  source_id: string;
}

export interface DigitalTwinConsistencyWarning {
  check: string;
  severity: "INFO" | "WARNING" | "ERROR";
  message: string;
  entity_type: string;
  entity_id: string;
}

export const digitalTwinApi = {
  getAssetSnapshot: (accessToken: string, assetId: string) =>
    apiRequest<DigitalTwinAssetSnapshot>(`/digital-twin/assets/${assetId}/snapshot`, { accessToken }),

  getAssetComponents: (accessToken: string, assetId: string) =>
    apiRequest<DigitalTwinComponentNode[]>(`/digital-twin/assets/${assetId}/components`, { accessToken }),

  getAssetTimeline: (accessToken: string, assetId: string) =>
    apiRequest<DigitalTwinTimelineEvent[]>(`/digital-twin/assets/${assetId}/timeline`, { accessToken }),

  getAssetConsistency: (accessToken: string, assetId: string) =>
    apiRequest<DigitalTwinConsistencyWarning[]>(`/digital-twin/assets/${assetId}/consistency`, { accessToken }),

  getComponentSnapshot: (accessToken: string, componentId: string) =>
    apiRequest<DigitalTwinComponentSnapshot>(`/digital-twin/components/${componentId}`, { accessToken }),

  getComponentGenealogy: (accessToken: string, componentId: string) =>
    apiRequest<DigitalTwinGenealogyEntry[]>(`/digital-twin/components/${componentId}/genealogy`, { accessToken }),

  getComponentTimeline: (accessToken: string, componentId: string) =>
    apiRequest<DigitalTwinTimelineEvent[]>(`/digital-twin/components/${componentId}/timeline`, { accessToken }),
};
