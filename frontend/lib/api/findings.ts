// Typed REAL-mode client for the backend Finding/Disposition endpoints
// (backend/app/api/v1/findings.py, M20.2). Distinct from
// lib/mock/findings.ts, which is a disconnected mock concept used only by
// the DEMO-mode dashboard checklist-exceptions widget — this talks to the
// real, tenant-scoped Finding model (backend/app/models/finding.py).
//
// Status: OPEN -> IN_PROGRESS -> CLOSED. A finding accumulates zero or more
// dispositions (CORRECTIVE_ACTION / NO_ACTION_REQUIRED / DEFERRED); closing
// requires at least one disposition to already exist.

import { apiRequest } from "@/lib/apiClient";

export interface BackendFindingDisposition {
  id: string;
  organization_id: string;
  finding_id: string;
  disposition_type: string;
  corrective_action: string | null;
  evidence_id: string | null;
  closed_at: string | null;
  closed_by_user_id: string | null;
  created_at: string;
}

export interface BackendFinding {
  id: string;
  organization_id: string;
  aircraft_id: string | null;
  asset_id: string | null;
  component_id: string | null;
  inspection_requirement_id: string | null;
  work_order_id: string | null;
  task_id: string | null;
  title: string;
  description: string;
  severity: string;
  status: string;
  discovered_at: string;
  discovered_by_user_id: string | null;
  responsible_user_id: string | null;
  created_at: string;
  updated_at: string;
  dispositions: BackendFindingDisposition[];
}

export const findingsApi = {
  create: (
    accessToken: string,
    payload: {
      title: string;
      description: string;
      severity: string;
      aircraft_id?: string;
      asset_id?: string;
      component_id?: string;
      inspection_requirement_id?: string;
      work_order_id?: string;
      task_id?: string;
      responsible_user_id?: string;
    }
  ) => apiRequest<BackendFinding>("/findings", { method: "POST", accessToken, body: payload }),

  get: (accessToken: string, findingId: string) =>
    apiRequest<BackendFinding>(`/findings/${findingId}`, { accessToken }),

  listForAircraft: (accessToken: string, aircraftId: string) =>
    apiRequest<BackendFinding[]>(`/findings?aircraft_id=${aircraftId}`, { accessToken }),

  /** Org-wide findings (no aircraft_id/asset_id filter) -- server always
   * scopes to the caller's organization_id regardless of filters. Used by
   * the dashboard's real Findings widget. Optional status filter matches
   * the backend's Finding.status values (OPEN / IN_PROGRESS / CLOSED). */
  listForOrganization: (accessToken: string, status?: string) =>
    apiRequest<BackendFinding[]>(
      `/findings${status ? `?status=${encodeURIComponent(status)}` : ""}`,
      { accessToken }
    ),

  addDisposition: (
    accessToken: string,
    findingId: string,
    payload: { disposition_type: string; corrective_action?: string; evidence_id?: string }
  ) =>
    apiRequest<BackendFinding>(`/findings/${findingId}/dispositions`, {
      method: "POST",
      accessToken,
      body: payload,
    }),

  close: (accessToken: string, findingId: string) =>
    apiRequest<BackendFinding>(`/findings/${findingId}/close`, { method: "POST", accessToken }),
};
