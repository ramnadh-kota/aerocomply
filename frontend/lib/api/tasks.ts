// Typed REAL-mode client for the backend Task endpoints. Tasks are a
// sub-resource of Work Orders in the backend (backend/app/api/v1/work_orders.py
// — POST/GET /work-orders/{work_order_id}/tasks) — there is no standalone
// /tasks collection endpoint, so list/create both take a work order id.

import { apiRequest } from "@/lib/apiClient";

export interface BackendTask {
  id: string;
  organization_id: string;
  work_order_id: string;
  description: string;
  execution_state: string;
  created_at: string;
}

export const tasksApi = {
  listForWorkOrder: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendTask[]>(`/work-orders/${workOrderId}/tasks`, { accessToken }),
};
