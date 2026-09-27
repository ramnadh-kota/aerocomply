// Typed REAL-mode client for the backend Task endpoints. Tasks are a
// sub-resource of Work Orders in the backend (backend/app/api/v1/work_orders.py
// — POST/GET /work-orders/{work_order_id}/tasks).

import { apiRequest } from "@/lib/apiClient";

export interface BackendTask {
  id: string;
  organization_id: string;
  work_order_id: string;
  description: string;
  task_number?: string | null;
  title?: string | null;
  execution_state: string;
  estimated_hours?: number | null;
  actual_hours?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  sequence?: number | null;
  assigned_technician_user_id?: string | null;
  evidence_required?: boolean;
  notes?: string | null;
  created_at: string;
}

export interface TaskCreatePayload {
  description: string;
  task_number?: string;
  title?: string;
  estimated_hours?: number;
  sequence?: number;
  assigned_technician_user_id?: string;
  evidence_required?: boolean;
  notes?: string;
}

export interface TaskUpdatePayload {
  description?: string;
  title?: string;
  estimated_hours?: number;
  actual_hours?: number;
  sequence?: number;
  assigned_technician_user_id?: string;
  evidence_required?: boolean;
  notes?: string;
}

export const tasksApi = {
  listForWorkOrder: (accessToken: string, workOrderId: string) =>
    apiRequest<BackendTask[]>(`/work-orders/${workOrderId}/tasks`, { accessToken }),

  create: (accessToken: string, workOrderId: string, payload: TaskCreatePayload) =>
    apiRequest<BackendTask>(`/work-orders/${workOrderId}/tasks`, {
      method: "POST",
      accessToken,
      body: payload,
    }),

  update: (accessToken: string, workOrderId: string, taskId: string, payload: TaskUpdatePayload) =>
    apiRequest<BackendTask>(`/work-orders/${workOrderId}/tasks/${taskId}`, {
      method: "PATCH",
      accessToken,
      body: payload,
    }),

  complete: (accessToken: string, workOrderId: string, taskId: string) =>
    apiRequest<BackendTask>(`/work-orders/${workOrderId}/tasks/${taskId}/complete`, {
      method: "POST",
      accessToken,
    }),
};
