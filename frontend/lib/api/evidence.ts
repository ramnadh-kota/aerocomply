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
  task_id: string;
  uploaded_by_user_id: string | null;
  status: string;
  reviewer_user_id: string | null;
  rejection_reason: string | null;
  created_at: string;
}

export const evidenceApi = {
  create: (accessToken: string, taskId: string) =>
    apiRequest<BackendEvidence>("/evidence", {
      method: "POST",
      accessToken,
      body: { task_id: taskId },
    }),

  get: (accessToken: string, evidenceId: string) =>
    apiRequest<BackendEvidence>(`/evidence/${evidenceId}`, { accessToken }),

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
