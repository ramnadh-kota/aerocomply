// Typed REAL-mode client for the backend Work Order endpoints
// (backend/app/api/v1/work_orders.py). organization_id is never sent by the
// client — the backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendWorkOrder {
  id: string;
  organization_id: string;
  aircraft_id: string;
  work_order_number: string;
  status: string;
  priority: string;
  created_by_user_id: string | null;
  created_at: string;
}

export const workOrdersApi = {
  list: (accessToken: string) => apiRequest<BackendWorkOrder[]>("/work-orders", { accessToken }),

  get: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}`, { accessToken }),
};
