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
  aircraft_id: string;
  requirement_id: string;
  status: string;
  evaluated_at: string;
  evaluated_by_user_id: string | null;
  notes: string | null;
  override_reason: string | null;
  overridden_by_user_id: string | null;
}

export interface ComplianceAssessmentCreateRequest {
  aircraft_id: string;
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

  /** Aggregate assessment counts by status for one aircraft, computed server-side
   * from directly-countable ComplianceAssessment rows only (see compliance_service
   * docstring — this is deliberately not the fuller "condition-tree confidence"
   * analytics the demo/mock layer shows, because no backend equivalent exists). */
  analyticsForAircraft: (accessToken: string, aircraftId: string) =>
    apiRequest<Record<string, number>>(`/aircraft/${aircraftId}/compliance-analytics`, {
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
