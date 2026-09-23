// Typed REAL-mode client for the backend Work Order endpoints
// (backend/app/api/v1/work_orders.py). organization_id is never sent by the
// client — the backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendWorkOrder {
  id: string;
  organization_id: string;
  aircraft_id: string | null;
  asset_id: string | null;
  work_order_number: string;
  status: string;
  priority: string;
  created_by_user_id: string | null;
  created_at: string;
}

export interface WorkOrderQueryParams {
  asset_id?: string;
  aircraft_id?: string;
}

function workOrderQuery(params?: WorkOrderQueryParams): string {
  if (!params) return "";
  const parts: string[] = [];
  if (params.asset_id) parts.push(`asset_id=${encodeURIComponent(params.asset_id)}`);
  if (params.aircraft_id) parts.push(`aircraft_id=${encodeURIComponent(params.aircraft_id)}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

export const workOrdersApi = {
  list: (accessToken: string, params?: WorkOrderQueryParams) =>
    apiRequest<BackendWorkOrder[]>(`/work-orders${workOrderQuery(params)}`, { accessToken }),

  get: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}`, { accessToken }),
};
