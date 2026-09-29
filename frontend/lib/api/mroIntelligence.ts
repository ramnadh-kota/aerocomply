// H7: MRO + Compliance + Readiness Intelligence Integration — typed client
// for the read-mostly correlation API (backend/app/api/v1/mro_intelligence.py).
// Every result here is a CORRELATION over existing authoritative outputs
// (HUMS H1-H5, aerospace_state_service, readiness_intelligence_service,
// maintenance, compliance) -- never a new system of record. This client
// mirrors backend/app/schemas/mro_intelligence.py field-for-field; it never
// invents fields or endpoints. organization_id is never sent -- the backend
// derives it from the authenticated JWT (same convention as every other
// lib/api/*.ts client).

import { apiRequest } from "@/lib/apiClient";

export type DataAvailability = "AVAILABLE" | "DATA_UNAVAILABLE";

export type ReadinessImpactLevel =
  | "NO_IMPACT"
  | "MONITOR"
  | "MAINTENANCE_DUE"
  | "INSPECTION_REQUIRED"
  | "REVIEW_REQUIRED"
  | "RESTRICTED_OPERATION"
  | "READINESS_AT_RISK"
  | "UNKNOWN";

export type OperationalImpactLevel = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";

export type ComplianceImpactState =
  | "COMPLIANT"
  | "NON_COMPLIANT"
  | "DUE"
  | "OVERDUE"
  | "UNKNOWN"
  | "NOT_APPLICABLE"
  | "REQUIRES_REVIEW";

export interface SourceLineageRef {
  source_type: string;
  source_id: string | null;
  label: string;
}

export interface MaintenanceCandidateOut {
  id: string;
  asset_id: string;
  component_id: string | null;
  candidate_type: string;
  status: string;
  priority: string;
  confidence: number;
  reason: string;
  dedup_key: string;
  source_lineage: Record<string, unknown>[];
  operational_impact: string | null;
  data_freshness: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  review_notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateActionRequest {
  notes?: string | null;
}

export interface ComplianceImpactObligation {
  obligation_id: string;
  requirement_id: string;
  state: string; // verbatim ComplianceState.value from ComplianceObligation
  impact: ComplianceImpactState;
  due_date: string | null;
  correlated_signals: SourceLineageRef[];
  explanation: string[];
}

export interface ComplianceImpactResult {
  asset_id: string;
  availability: DataAvailability;
  obligations: ComplianceImpactObligation[];
  overall_impact: ComplianceImpactState;
  explanation: string[];
  evaluated_at: string;
}

export interface ReadinessImpactResult {
  asset_id: string;
  authoritative_readiness_state: "READY" | "BLOCKED" | "UNKNOWN";
  readiness_impact: ReadinessImpactLevel;
  contributing_factors: SourceLineageRef[];
  explanation: string[];
  evaluated_at: string;
}

export interface OperationalImpactResult {
  asset_id: string;
  impact_level: OperationalImpactLevel;
  reason: string;
  contributing_factors: SourceLineageRef[];
  evaluated_at: string;
}

export interface IntegrationConflict {
  check: string;
  description: string;
  source_a: SourceLineageRef;
  source_b: SourceLineageRef;
  severity: "LOW" | "MEDIUM" | "HIGH";
}

export interface ReconciliationResult {
  asset_id: string;
  resolved_candidate_ids: string[];
  flagged_candidate_ids: string[];
  explanation: string[];
  evaluated_at: string;
}

export interface AssetMROIntelligence {
  asset_id: string;
  availability: DataAvailability;
  health_state: string | null;
  health_confidence: string | null;
  open_diagnostic_count: number;
  open_prognostic_alert_count: number;
  authoritative_readiness_state: "READY" | "BLOCKED" | "UNKNOWN";
  readiness_impact: ReadinessImpactLevel;
  compliance_impact: ComplianceImpactState;
  operational_impact: OperationalImpactLevel;
  open_candidate_count: number;
  candidates: MaintenanceCandidateOut[];
  conflicts: IntegrationConflict[];
  explanation: string[];
  evaluated_at: string;
}

export const mroIntelligenceApi = {
  getAssetMROIntelligence: (accessToken: string, assetId: string) =>
    apiRequest<AssetMROIntelligence>(`/mro-intelligence/assets/${assetId}`, { accessToken }),

  listMaintenanceCandidates: (accessToken: string, assetId: string) =>
    apiRequest<MaintenanceCandidateOut[]>(`/mro-intelligence/assets/${assetId}/maintenance-candidates`, { accessToken }),

  getComplianceImpact: (accessToken: string, assetId: string) =>
    apiRequest<ComplianceImpactResult>(`/mro-intelligence/assets/${assetId}/compliance-impact`, { accessToken }),

  getReadinessImpact: (accessToken: string, assetId: string) =>
    apiRequest<ReadinessImpactResult>(`/mro-intelligence/assets/${assetId}/readiness-impact`, { accessToken }),

  getOperationalImpact: (accessToken: string, assetId: string) =>
    apiRequest<OperationalImpactResult>(`/mro-intelligence/assets/${assetId}/operational-impact`, { accessToken }),

  getConflicts: (accessToken: string, assetId: string) =>
    apiRequest<IntegrationConflict[]>(`/mro-intelligence/assets/${assetId}/conflicts`, { accessToken }),

  reconcileAsset: (accessToken: string, assetId: string) =>
    apiRequest<ReconciliationResult>(`/mro-intelligence/assets/${assetId}/reconcile`, { accessToken, method: "POST" }),

  getComponentMROIntelligence: (accessToken: string, componentId: string) =>
    apiRequest<Record<string, unknown>>(`/mro-intelligence/components/${componentId}`, { accessToken }),

  getCandidate: (accessToken: string, candidateId: string) =>
    apiRequest<MaintenanceCandidateOut>(`/mro-intelligence/candidates/${candidateId}`, { accessToken }),

  reviewCandidate: (accessToken: string, candidateId: string, body: CandidateActionRequest = {}) =>
    apiRequest<MaintenanceCandidateOut>(`/mro-intelligence/candidates/${candidateId}/review`, {
      accessToken,
      method: "POST",
      body,
    }),

  acceptCandidate: (accessToken: string, candidateId: string, body: CandidateActionRequest = {}) =>
    apiRequest<MaintenanceCandidateOut>(`/mro-intelligence/candidates/${candidateId}/accept`, {
      accessToken,
      method: "POST",
      body,
    }),

  rejectCandidate: (accessToken: string, candidateId: string, body: CandidateActionRequest = {}) =>
    apiRequest<MaintenanceCandidateOut>(`/mro-intelligence/candidates/${candidateId}/reject`, {
      accessToken,
      method: "POST",
      body,
    }),

  deferCandidate: (accessToken: string, candidateId: string, body: CandidateActionRequest = {}) =>
    apiRequest<MaintenanceCandidateOut>(`/mro-intelligence/candidates/${candidateId}/defer`, {
      accessToken,
      method: "POST",
      body,
    }),
};
