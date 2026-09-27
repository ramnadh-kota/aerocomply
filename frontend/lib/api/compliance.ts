// Typed REAL-mode client for the backend Compliance endpoints
// (backend/app/api/v1/compliance.py, backend/app/services/compliance_service.py).
// organization_id is never sent by the client — the backend derives it from
// the authenticated JWT.
//
// IMPORTANT — data-honesty note (see docs/FULL_SYSTEM_AUDIT.md §7/§13, BL-09):
// backend/app/services/ai/tools.py explicitly documents that "Regulatory
// applicability rules (condition-tree evaluation) ... remain NOT
// backend-resident". ComplianceAssessment rows here are manually recorded
// determinations (created/overridden by a human via the API), never the
// output of an automated regulatory applicability engine. Nothing in this
// client or the pages that use it should be worded to imply otherwise.

import { apiRequest } from "@/lib/apiClient";

export interface BackendRegulatoryRequirement {
  id: string;
  organization_id: string;
  authority: string;
  regulatory_document_id: string | null;
  requirement_number: string;
  title: string;
  description: string;
  effective_date: string | null;
  compliance_time: string | null;
  source_url: string | null;
}

export interface BackendComplianceAssessment {
  id: string;
  organization_id: string;
  aircraft_id: string | null;
  asset_id: string | null;
  requirement_id: string;
  status: string;
  evaluated_at: string;
  evaluated_by_user_id: string | null;
  notes: string | null;
  override_reason: string | null;
  overridden_by_user_id: string | null;
}

export interface ComplianceAssessmentCreateRequest {
  aircraft_id?: string | null;
  asset_id?: string | null;
  requirement_id: string;
  status?: string;
  evaluated_at: string;
  notes?: string | null;
}

export interface ComplianceAssessmentOverrideRequest {
  status: string;
  override_reason: string;
}

export const regulatoryRequirementsApi = {
  list: (accessToken: string) =>
    apiRequest<BackendRegulatoryRequirement[]>("/regulatory-requirements", { accessToken }),

  get: (accessToken: string, requirementId: string) =>
    apiRequest<BackendRegulatoryRequirement>(`/regulatory-requirements/${requirementId}`, {
      accessToken,
    }),
};

export const complianceAssessmentsApi = {
  listForAircraft: (accessToken: string, aircraftId: string) =>
    apiRequest<BackendComplianceAssessment[]>(
      `/aircraft/${aircraftId}/compliance-assessments`,
      { accessToken }
    ),

  listForAsset: (accessToken: string, assetId: string) =>
    apiRequest<BackendComplianceAssessment[]>(
      `/assets/${assetId}/compliance-assessments`,
      { accessToken }
    ),

  analyticsForAircraft: (accessToken: string, aircraftId: string) =>
    apiRequest<Record<string, number>>(`/aircraft/${aircraftId}/compliance-analytics`, {
      accessToken,
    }),

  analyticsForAsset: (accessToken: string, assetId: string) =>
    apiRequest<Record<string, number>>(`/assets/${assetId}/compliance-analytics`, {
      accessToken,
    }),

  get: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendComplianceAssessment>(`/compliance-assessments/${assessmentId}`, {
      accessToken,
    }),

  create: (accessToken: string, payload: ComplianceAssessmentCreateRequest) =>
    apiRequest<BackendComplianceAssessment>("/compliance-assessments", {
      method: "POST",
      body: payload,
      accessToken,
    }),

  override: (accessToken: string, assessmentId: string, payload: ComplianceAssessmentOverrideRequest) =>
    apiRequest<BackendComplianceAssessment>(`/compliance-assessments/${assessmentId}/override`, {
      method: "POST",
      body: payload,
      accessToken,
    }),
};

export interface BackendComplianceObligation {
  id: string;
  organization_id: string;
  requirement_id: string;
  rule_id: string | null;
  asset_id: string | null;
  aircraft_id: string | null;
  applicability_evaluation_id: string | null;
  status: string;
  priority: string;
  due_date: string | null;
  recurrence: string | null;
  responsible_role: string | null;
  responsible_user_id: string | null;
  required_action: string | null;
  evidence_requirements: Array<{ type: string; description: string }> | null;
  completed_at: string | null;
  verified_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BackendComplianceOverview {
  total_obligations: number;
  applicable_requirements: number;
  due_count: number;
  overdue_count: number;
  in_progress_count: number;
  compliant_count: number;
  non_compliant_count: number;
  blocked_count: number;
  review_required_count: number;
  not_applicable_count: number;
  compliance_rate_percent: number;
  status_distribution: Record<string, number>;
}

export interface BackendTraceabilityEvidence {
  id: string;
  title: string | null;
  evidence_type: string | null;
  source: string | null;
  captured_at: string | null;
  verification_status: string;
  verified_at: string | null;
  verifier: string | null;
  rejection_reason: string | null;
}

export interface BackendComplianceTraceability {
  obligation_id: string;
  requirement_id: string;
  requirement_number: string;
  requirement_title: string;
  compliance_state: string;
  is_compliant: boolean;
  is_verified: boolean;
  why_applies: {
    evaluation_id?: string | null;
    rule_id?: string | null;
    rule_code?: string | null;
    rule_title?: string | null;
    system_result?: string | null;
    is_applicable?: boolean | null;
    evaluated_at?: string | null;
    reasoning_trace?: string[] | null;
    condition_tree_summary?: any;
    note?: string;
  };
  what_action_required: {
    action: string;
    priority: string;
    due_date?: string | null;
    recurrence?: string | null;
    responsible_role?: string | null;
    completed_at?: string | null;
  };
  what_evidence_required: Array<{ type: string; description: string }>;
  provided_evidence: BackendTraceabilityEvidence[];
  why_current_state: string;
  blockers: string[];
  asset: {
    asset_id?: string | null;
    aircraft_id?: string | null;
    identifier: string;
    variant: string;
  };
}

export interface ComplianceObligationCreateRequest {
  requirement_id: string;
  rule_id?: string | null;
  asset_id?: string | null;
  aircraft_id?: string | null;
  priority?: string;
  due_date?: string | null;
  recurrence?: string | null;
  responsible_role?: string | null;
  required_action?: string | null;
  evidence_requirements?: Array<{ type: string; description: string }>;
  notes?: string | null;
}

export const complianceObligationsApi = {
  overview: (accessToken: string) =>
    apiRequest<BackendComplianceOverview>("/compliance/overview", { accessToken }),

  list: (
    accessToken: string,
    filters?: {
      status?: string;
      aircraft_id?: string;
      asset_id?: string;
      requirement_id?: string;
    }
  ) => {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.aircraft_id) params.set("aircraft_id", filters.aircraft_id);
    if (filters?.asset_id) params.set("asset_id", filters.asset_id);
    if (filters?.requirement_id) params.set("requirement_id", filters.requirement_id);
    const qs = params.toString() ? `?${params.toString()}` : "";
    return apiRequest<BackendComplianceObligation[]>(`/compliance/obligations${qs}`, {
      accessToken,
    });
  },

  get: (accessToken: string, id: string) =>
    apiRequest<BackendComplianceObligation>(`/compliance/obligations/${id}`, {
      accessToken,
    }),

  create: (accessToken: string, payload: ComplianceObligationCreateRequest) =>
    apiRequest<BackendComplianceObligation>("/compliance/obligations", {
      method: "POST",
      body: payload,
      accessToken,
    }),

  evaluate: (accessToken: string, id: string) =>
    apiRequest<BackendComplianceObligation>(`/compliance/obligations/${id}/evaluate`, {
      method: "POST",
      accessToken,
    }),

  traceability: (accessToken: string, id: string) =>
    apiRequest<BackendComplianceTraceability>(`/compliance/obligations/${id}/traceability`, {
      accessToken,
    }),

  listEvidence: (accessToken: string, id: string) =>
    apiRequest<any[]>(`/compliance/obligations/${id}/evidence`, {
      accessToken,
    }),

  attachEvidence: (accessToken: string, id: string, payload: any) =>
    apiRequest<any>(`/compliance/obligations/${id}/evidence`, {
      method: "POST",
      body: payload,
      accessToken,
    }),
};

// ---------------------------------------------------------------------------
// D2-3 Compliance Intelligence & Readiness Gate Integration
// ---------------------------------------------------------------------------

export interface ComplianceReadinessBlocker {
  blocker_id: string;
  category: string;
  what_blocking: string;
  why_blocking: string;
  source_record_type: string;
  source_record_id: string;
  regulatory_requirement_number: string | null;
  regulatory_requirement_title: string | null;
  required_action: string | null;
  missing_evidence: string | null;
  resolution_action: string;
}

export interface ComplianceReadinessContribution {
  asset_id: string;
  aircraft_id: string | null;
  overall_status: "READY" | "BLOCKED" | "REVIEW_REQUIRED" | "UNKNOWN" | string;
  blockers: ComplianceReadinessBlocker[];
  warnings: string[];
  compliance_obligations_count: number;
  compliant_obligations_count: number;
  overdue_obligations_count: number;
  critical_findings_count: number;
  missing_evidence_count: number;
  rejected_evidence_count: number;
  review_required_count: number;
  source_records: Array<Record<string, any>>;
  evaluated_at: string;
}

export interface FindingComplianceImpact {
  finding_id: string;
  title: string;
  severity: string;
  status: string;
  safety_significance: string | null;
  compliance_relevance: string | null;
  asset_id: string | null;
  aircraft_id: string | null;
  component_id: string | null;
  work_order_id: string | null;
  inspection_requirement_id: string | null;
  compliance_obligation_id: string | null;
  regulatory_requirement_id: string | null;
  regulatory_requirement_number: string | null;
  regulatory_requirement_title: string | null;
  current_compliance_state: string | null;
  corrective_action_required: string | null;
  evidence_status: string | null;
  evidence_verification_status: string | null;
  is_readiness_blocker: boolean;
  blocker_reason: string | null;
}

export interface InspectionComplianceImpact {
  inspection_requirement_id: string;
  status: string;
  required: boolean;
  inspector_user_id: string | null;
  work_order_id: string | null;
  task_id: string | null;
  asset_id: string | null;
  aircraft_id: string | null;
  compliance_obligation_id: string | null;
  regulatory_requirement_id: string | null;
  regulatory_requirement_number: string | null;
  current_compliance_state: string | null;
  associated_findings: Array<{ id: string; title: string; severity: string; status: string }>;
  attached_evidence: Array<{ id: string; title: string; verification_status: string; status: string }>;
  is_readiness_blocker: boolean;
  blocker_reason: string | null;
}

export interface AssetComplianceImpact {
  asset_id: string;
  aircraft_id: string | null;
  overall_status: string;
  readiness_contribution: ComplianceReadinessContribution;
  active_blockers: ComplianceReadinessBlocker[];
  critical_findings: FindingComplianceImpact[];
  overdue_obligations: Array<{ id: string; requirement_id: string; status: string; due_date: string | null; required_action: string | null }>;
  missing_or_rejected_evidence: Array<{ id: string; title: string; verification_status: string; status: string; rejection_reason: string | null }>;
  inspections_requiring_action: InspectionComplianceImpact[];
}

export const complianceIntelligenceApi = {
  getAssetReadiness: (accessToken: string, assetId: string) =>
    apiRequest<ComplianceReadinessContribution>(`/compliance/assets/${assetId}/readiness`, { accessToken }),

  getAssetImpact: (accessToken: string, assetId: string) =>
    apiRequest<AssetComplianceImpact>(`/compliance/assets/${assetId}/impact`, { accessToken }),

  getFindingImpact: (accessToken: string, findingId: string) =>
    apiRequest<FindingComplianceImpact>(`/compliance/findings/${findingId}/impact`, { accessToken }),

  getInspectionImpact: (accessToken: string, inspectionId: string) =>
    apiRequest<InspectionComplianceImpact>(`/compliance/inspections/${inspectionId}/impact`, { accessToken }),

  resolveInspection: (accessToken: string, inspectionId: string) =>
    apiRequest<{ resolved: boolean; reason?: string; obligation_id?: string; obligation_status?: string; inspection_status: string }>(
      `/compliance/inspections/${inspectionId}/resolve`,
      { method: "POST", accessToken }
    ),
};

