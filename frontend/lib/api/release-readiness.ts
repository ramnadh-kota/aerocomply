// Typed REAL-mode client for GET /work-orders/{id}/release-readiness
// (backend/app/api/v1/release_readiness.py,
// backend/app/services/release_readiness_service.py,
// backend/app/schemas/release_readiness.py). This is a pure read: the
// backend aggregates Task/Evidence/InspectionRequirement gate status for a
// work order and returns it verbatim. Never re-derive or add blocker
// categories on the frontend — only these three exist today.

import { apiRequest } from "@/lib/apiClient";

export type BackendBlockerCategory = "EVIDENCE" | "INSPECTION" | "TASK_EXECUTION";
export type BackendReadinessStatus = "READY" | "BLOCKED" | "UNKNOWN";

export interface BackendBlocker {
  category: BackendBlockerCategory;
  description: string;
  related_record_id: string;
}

export interface BackendReleaseReadiness {
  work_order_id: string;
  status: BackendReadinessStatus;
  blockers: BackendBlocker[];
  data_completeness: string;
}

export const releaseReadinessApi = {
  getForWorkOrder: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendReleaseReadiness>(`/work-orders/${workOrderId}/release-readiness`, {
      accessToken,
    }),
};
