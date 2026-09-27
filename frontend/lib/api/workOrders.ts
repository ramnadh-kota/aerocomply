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
  title: string | null;
  description: string | null;
  work_order_type: string | null;
  maintenance_category: string | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  due_at: string | null;
  estimated_hours: number | null;
  actual_hours: number | null;
  estimated_cost: number | null;
  actual_cost: number | null;
  assigned_to_user_id: string | null;
  location: string | null;
  source_type: string | null;
  source_reference: string | null;
  compliance_required: boolean;
  compliance_reference: string | null;
  completed_at: string | null;
  closed_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string | null;
  deleted_at: string | null;
}

export interface WorkOrderQueryParams {
  asset_id?: string;
  aircraft_id?: string;
  status?: string;
  priority?: string;
  work_order_type?: string;
  assigned_to_user_id?: string;
  search?: string;
  overdue_only?: boolean;
  limit?: number;
  offset?: number;
}

export interface WorkOrderCreatePayload {
  work_order_number: string;
  aircraft_id?: string | null;
  asset_id?: string | null;
  priority?: string;
  title?: string | null;
  description?: string | null;
  work_order_type?: string | null;
  maintenance_category?: string | null;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  due_at?: string | null;
  estimated_hours?: number | null;
  estimated_cost?: number | null;
  assigned_to_user_id?: string | null;
  location?: string | null;
  source_type?: string | null;
  source_reference?: string | null;
  compliance_required?: boolean;
  compliance_reference?: string | null;
}

export interface WorkOrderUpdatePayload {
  priority?: string;
  title?: string | null;
  description?: string | null;
  work_order_type?: string | null;
  maintenance_category?: string | null;
  scheduled_start?: string | null;
  scheduled_end?: string | null;
  actual_start?: string | null;
  actual_end?: string | null;
  due_at?: string | null;
  estimated_hours?: number | null;
  actual_hours?: number | null;
  estimated_cost?: number | null;
  actual_cost?: number | null;
  assigned_to_user_id?: string | null;
  location?: string | null;
  source_type?: string | null;
  source_reference?: string | null;
  compliance_required?: boolean;
  compliance_reference?: string | null;
}

export interface WorkOrderAssignPayload {
  assigned_to_user_id: string;
}

export interface WorkOrderTransitionPayload {
  target_status: string;
  reason?: string;
}

export interface WorkOrderCancelPayload {
  cancellation_reason: string;
}

export interface TatStatusResponse {
  work_order_id: string;
  status: "ON_TRACK" | "AT_RISK" | "DELAYED" | "UNKNOWN";
  due_date: string | null;
  days_remaining: number | null;
  days_overdue: number | null;
  reason: string;
}

export interface FleetTatSummaryResponse {
  organization_id: string;
  on_track_count: number;
  at_risk_count: number;
  delayed_count: number;
  unknown_count: number;
  total_work_orders: number;
  reason: string;
}

function workOrderQuery(params?: WorkOrderQueryParams): string {
  if (!params) return "";
  const parts: string[] = [];
  if (params.asset_id) parts.push(`asset_id=${encodeURIComponent(params.asset_id)}`);
  if (params.aircraft_id) parts.push(`aircraft_id=${encodeURIComponent(params.aircraft_id)}`);
  if (params.status) parts.push(`status=${encodeURIComponent(params.status)}`);
  if (params.priority) parts.push(`priority=${encodeURIComponent(params.priority)}`);
  if (params.work_order_type) parts.push(`work_order_type=${encodeURIComponent(params.work_order_type)}`);
  if (params.assigned_to_user_id) parts.push(`assigned_to_user_id=${encodeURIComponent(params.assigned_to_user_id)}`);
  if (params.search) parts.push(`search=${encodeURIComponent(params.search)}`);
  if (params.overdue_only !== undefined) parts.push(`overdue_only=${encodeURIComponent(String(params.overdue_only))}`);
  if (params.limit !== undefined) parts.push(`limit=${encodeURIComponent(String(params.limit))}`);
  if (params.offset !== undefined) parts.push(`offset=${encodeURIComponent(String(params.offset))}`);
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

export const workOrdersApi = {
  list: (accessToken: string, params?: WorkOrderQueryParams) =>
    apiRequest<BackendWorkOrder[]>(`/work-orders${workOrderQuery(params)}`, { accessToken }),

  get: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}`, { accessToken }),

  create: (accessToken: string, payload: WorkOrderCreatePayload) =>
    apiRequest<BackendWorkOrder>("/work-orders", {
      method: "POST",
      accessToken,
      body: payload,
    }),

  update: (accessToken: string, workOrderId: string, payload: WorkOrderUpdatePayload) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}`, {
      method: "PATCH",
      accessToken,
      body: payload,
    }),

  assign: (accessToken: string, workOrderId: string, payload: WorkOrderAssignPayload) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}/assign`, {
      method: "POST",
      accessToken,
      body: payload,
    }),

  transition: (accessToken: string, workOrderId: string, payload: WorkOrderTransitionPayload) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}/transition`, {
      method: "POST",
      accessToken,
      body: payload,
    }),

  complete: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}/complete`, {
      method: "POST",
      accessToken,
    }),

  close: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}/close`, {
      method: "POST",
      accessToken,
    }),

  cancel: (accessToken: string, workOrderId: string, payload: WorkOrderCancelPayload) =>
    apiRequest<BackendWorkOrder>(`/work-orders/${workOrderId}/cancel`, {
      method: "POST",
      accessToken,
      body: payload,
    }),

  delete: (accessToken: string, workOrderId: string) =>
    apiRequest<{ id: string; status: string }>(`/work-orders/${workOrderId}`, {
      method: "DELETE",
      accessToken,
    }),

  getTat: (accessToken: string, workOrderId: string) =>
    apiRequest<TatStatusResponse>(`/work-orders/${workOrderId}/tat`, { accessToken }),

  getFleetTat: (accessToken: string) =>
    apiRequest<FleetTatSummaryResponse>("/fleet/tat", { accessToken }),
};
