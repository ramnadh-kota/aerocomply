// Typed REAL-mode client for the backend Assessment domain
// (backend/app/api/v1/assessments.py). organization_id is never sent — the
// backend derives it from the JWT. Scoring/comparison logic is never
// recomputed here — every field below is exactly what the backend returned.

import { apiRequest } from "@/lib/apiClient";

export interface BackendAssessment {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  scope_type: "FLEET" | "AIRCRAFT" | "WORK_ORDER";
  scope_id: string | null;
  status: "DRAFT" | "RUNNING" | "COMPLETE" | "FAILED";
  created_by_user_id: string | null;
  created_at: string;
}

export interface BackendAssessmentSnapshot {
  id: string;
  assessment_id: string;
  version: number;
  overall_score: number;
  maturity_band: string;
  summary: string | null;
  finding_count: number;
  critical_finding_count: number;
  created_at: string;
}

export interface BackendAssessmentFinding {
  id: string;
  category: string;
  severity: string;
  title: string;
  description: string;
  entity_type: string;
  entity_id: string;
  materiality_score: number;
  complexity_band: string;
  dependency_count: number;
  impact_dimensions: string[];
  priority_rank: number;
  source: string;
  resolved: boolean;
}

export interface BackendAssessmentRisk {
  id: string;
  finding_id: string | null;
  risk_level: string;
  likelihood: string;
  reason: string;
  entity_type: string;
  entity_id: string;
  mitigation: string | null;
  owner_role: string | null;
}

export interface BackendAssessmentGap {
  id: string;
  finding_id: string | null;
  category: string;
  severity: string;
  entity_type: string;
  entity_id: string;
  expected_condition: string;
  current_condition: string;
  recommended_action: string;
}

export interface BackendAssessmentRecommendation {
  id: string;
  finding_id: string | null;
  recommendation: string;
  why: string;
  priority: string;
  responsible_role: string | null;
  entity_type: string;
  entity_id: string;
  status: string;
}

export interface BackendAssessmentRoadmapItem {
  id: string;
  finding_id: string | null;
  sequence: number;
  title: string;
  description: string;
  category: string;
  priority: string;
  status: string;
  entity_type: string;
  entity_id: string;
  prerequisite_sequence_numbers: number[];
  owner_role: string | null;
  estimated_effort_band: string;
  effort_confidence: string;
  expected_impact: string;
  risk_if_delayed: string;
}

export interface BackendAssessmentSnapshotComparison {
  from_version: number;
  to_version: number;
  score_delta: number;
  new_findings: BackendAssessmentFinding[];
  resolved_findings: string[];
}

export interface AssessmentCreatePayload {
  name: string;
  description?: string;
  scope_type?: "FLEET" | "AIRCRAFT" | "WORK_ORDER";
  scope_id?: string;
}

export const assessmentsApi = {
  list: (accessToken: string) => apiRequest<BackendAssessment[]>("/assessments", { accessToken }),

  create: (accessToken: string, payload: AssessmentCreatePayload) =>
    apiRequest<BackendAssessment>("/assessments", { method: "POST", body: payload, accessToken }),

  get: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessment>(`/assessments/${assessmentId}`, { accessToken }),

  run: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentSnapshot>(`/assessments/${assessmentId}/run`, {
      method: "POST",
      accessToken,
    }),

  getLatestSnapshot: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentSnapshot>(`/assessments/${assessmentId}/snapshot`, { accessToken }),

  getFindings: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentFinding[]>(`/assessments/${assessmentId}/findings`, { accessToken }),

  getRisks: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentRisk[]>(`/assessments/${assessmentId}/risks`, { accessToken }),

  getGaps: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentGap[]>(`/assessments/${assessmentId}/gaps`, { accessToken }),

  getRecommendations: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentRecommendation[]>(`/assessments/${assessmentId}/recommendations`, {
      accessToken,
    }),

  getRoadmap: (accessToken: string, assessmentId: string) =>
    apiRequest<BackendAssessmentRoadmapItem[]>(`/assessments/${assessmentId}/roadmap`, {
      accessToken,
    }),

  compareSnapshots: (accessToken: string, snapshotIdA: string, snapshotIdB: string) =>
    apiRequest<BackendAssessmentSnapshotComparison>(
      `/assessments/compare/${snapshotIdA}/${snapshotIdB}`,
      { accessToken }
    ),
};
