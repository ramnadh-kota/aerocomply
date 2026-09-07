// Typed REAL-mode client for the backend InspectionRequirement endpoints
// (backend/app/api/v1/inspections.py). Two distinct concepts share this one
// resource, distinguished only by `required`
// (backend/app/services/inspection_service.py):
//   - required === false -> checklist-style review, any authorized reviewer
//     may close it out, no independence constraint.
//   - required === true  -> RII (Required Inspection Item). Completing it
//     needs an inspector_user_id who did NOT upload evidence for the same
//     task. The backend enforces this — never re-derive it in the UI.
//
// Status: PENDING -> COMPLETED / NOT_REQUIRED / REJECTED (REJECTED can
// return to PENDING). Only COMPLETED or NOT_REQUIRED satisfy the
// completion gate.

import { apiRequest } from "@/lib/apiClient";

export interface BackendInspectionRequirement {
  id: string;
  organization_id: string;
  task_id: string | null;
  work_order_id: string | null;
  required: boolean;
  inspector_user_id: string | null;
  status: string;
  rejection_reason: string | null;
  created_at: string;
}

export const inspectionsApi = {
  create: (
    accessToken: string,
    payload: { task_id?: string; work_order_id?: string; required?: boolean }
  ) =>
    apiRequest<BackendInspectionRequirement>("/inspections", {
      method: "POST",
      accessToken,
      body: payload,
    }),

  get: (accessToken: string, requirementId: string) =>
    apiRequest<BackendInspectionRequirement>(`/inspections/${requirementId}`, { accessToken }),

  listForWorkOrder: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendInspectionRequirement[]>(
      `/inspections/by-work-order/${workOrderId}`,
      { accessToken }
    ),

  transition: (
    accessToken: string,
    requirementId: string,
    targetStatus: string,
    opts?: { inspectorUserId?: string; rejectionReason?: string }
  ) =>
    apiRequest<BackendInspectionRequirement>(`/inspections/${requirementId}/transition`, {
      method: "POST",
      accessToken,
      body: {
        target_status: targetStatus,
        inspector_user_id: opts?.inspectorUserId ?? null,
        rejection_reason: opts?.rejectionReason ?? null,
      },
    }),
};
