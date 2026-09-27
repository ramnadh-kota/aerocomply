// Typed REAL-mode client for the backend Evidence endpoints
// (backend/app/api/v1/evidence.py). Evidence is a status-tracking record
// keyed to a real task_id — there is no file upload field on the backend
// schema, so this is a lifecycle/status API, not a file upload API.
//
// Lifecycle: REQUIRED -> UPLOADED -> SUBMITTED -> AWAITING_REVIEW ->
// ACCEPTED/REJECTED. Only ACCEPTED satisfies the completion gate
// (backend/app/services/evidence_service.py::satisfies_completion_gate).
// The frontend never recreates this state machine — every change goes
// through POST /evidence/{id}/transition and the UI renders whatever
// status the response comes back with.

import { apiRequest } from "@/lib/apiClient";

export interface BackendEvidence {
  id: string;
  organization_id: string;
  task_id: string | null;
  compliance_obligation_id?: string | null;
  regulatory_requirement_id?: string | null;
  asset_id?: string | null;
  aircraft_id?: string | null;
  component_id?: string | null;
  inspection_requirement_id?: string | null;
  finding_id?: string | null;
  work_order_id?: string | null;
  title?: string | null;
  description?: string | null;
  evidence_type?: string | null;
  source?: string | null;
  captured_at?: string | null;
  uploaded_by_user_id: string | null;
  status: string;
  verification_status?: string;
  verifier_user_id?: string | null;
  verified_at?: string | null;
  verification_notes?: string | null;
  reviewer_user_id: string | null;
  rejection_reason: string | null;
  provenance?: Record<string, any> | null;
  created_at: string;
  updated_at?: string;
}

export interface EvidenceCreatePayload {
  task_id?: string | null;
  compliance_obligation_id?: string | null;
  regulatory_requirement_id?: string | null;
  asset_id?: string | null;
  aircraft_id?: string | null;
  component_id?: string | null;
  inspection_requirement_id?: string | null;
  finding_id?: string | null;
  work_order_id?: string | null;
  title?: string | null;
  description?: string | null;
  evidence_type?: string | null;
  source?: string | null;
  captured_at?: string | null;
  provenance?: Record<string, any> | null;
}

export const evidenceApi = {
  create: (accessToken: string, payload: EvidenceCreatePayload | string) => {
    const body = typeof payload === "string" ? { task_id: payload } : payload;
    return apiRequest<BackendEvidence>("/evidence", {
      method: "POST",
      accessToken,
      body,
    });
  },

  get: (accessToken: string, evidenceId: string) =>
    apiRequest<BackendEvidence>(`/evidence/${evidenceId}`, { accessToken }),

  verify: (accessToken: string, evidenceId: string, notes?: string) =>
    apiRequest<BackendEvidence>(`/evidence/${evidenceId}/verify`, {
      method: "POST",
      accessToken,
      body: { verification_notes: notes ?? null },
    }),

  reject: (accessToken: string, evidenceId: string, reason: string) =>
    apiRequest<BackendEvidence>(`/evidence/${evidenceId}/reject`, {
      method: "POST",
      accessToken,
      body: { rejection_reason: reason },
    }),

  transition: (
    accessToken: string,
    evidenceId: string,
    targetStatus: string,
    rejectionReason?: string
  ) =>
    apiRequest<BackendEvidence>(`/evidence/${evidenceId}/transition`, {
      method: "POST",
      accessToken,
      body: { target_status: targetStatus, rejection_reason: rejectionReason ?? null },
    }),
};
