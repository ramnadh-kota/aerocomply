// Typed REAL-mode client for the backend Procurement Request endpoints
// (backend/app/api/v1/procurement.py). organization_id is never sent — the
// backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendProcurementRequest {
  id: string;
  organization_id: string;
  aircraft_id: string;
  work_order_id: string | null;
  task_id: string | null;
  part_id: string | null;
  part_number: string;
  description: string;
  quantity: number;
  priority: string;
  reason: string;
  requested_by_user_id: string | null;
  preferred_vendor_id: string | null;
  selected_vendor_id: string | null;
  status: string;
  estimated_cost_cents: number | null;
  approved_by_user_id: string | null;
  rejection_reason: string | null;
  clarification_note: string | null;
  created_at: string;
}

export const procurementRequestsApi = {
  list: (accessToken: string, status?: string) =>
    apiRequest<BackendProcurementRequest[]>(
      `/procurement-requests${status ? `?status=${status}` : ""}`,
      { accessToken }
    ),
  get: (accessToken: string, id: string) =>
    apiRequest<BackendProcurementRequest>(`/procurement-requests/${id}`, { accessToken }),
};
