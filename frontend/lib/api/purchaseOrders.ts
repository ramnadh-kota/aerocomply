// Typed REAL-mode client for the backend Purchase Order + Receiving
// endpoints (backend/app/api/v1/purchase_orders.py,
// backend/app/api/v1/receiving.py). organization_id is never sent — the
// backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendPurchaseOrderLine {
  id: string;
  purchase_order_id: string;
  procurement_request_id: string | null;
  part_number: string;
  description: string;
  quantity: number;
  unit_price_cents: number | null;
  received_quantity: number;
}

export interface BackendPurchaseOrder {
  id: string;
  organization_id: string;
  po_number: string;
  vendor_id: string;
  aircraft_id: string | null;
  status: string;
  currency: string;
  subtotal_cents: number;
  tax_cents: number | null;
  shipping_cents: number | null;
  total_cents: number;
  required_by: string | null;
  expected_delivery: string | null;
  notes: string | null;
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  lines: BackendPurchaseOrderLine[];
  created_at: string;
}

export const purchaseOrdersApi = {
  list: (accessToken: string, status?: string) =>
    apiRequest<BackendPurchaseOrder[]>(`/purchase-orders${status ? `?status=${status}` : ""}`, {
      accessToken,
    }),
  get: (accessToken: string, id: string) =>
    apiRequest<BackendPurchaseOrder>(`/purchase-orders/${id}`, { accessToken }),
  submitForApproval: (accessToken: string, id: string) =>
    apiRequest<BackendPurchaseOrder>(`/purchase-orders/${id}/submit-for-approval`, {
      method: "POST",
      accessToken,
    }),
  approve: (accessToken: string, id: string) =>
    apiRequest<BackendPurchaseOrder>(`/purchase-orders/${id}/approve`, {
      method: "POST",
      accessToken,
    }),
  send: (accessToken: string, id: string) =>
    apiRequest<BackendPurchaseOrder>(`/purchase-orders/${id}/send`, {
      method: "POST",
      accessToken,
    }),
  cancel: (accessToken: string, id: string) =>
    apiRequest<BackendPurchaseOrder>(`/purchase-orders/${id}/cancel`, {
      method: "POST",
      accessToken,
    }),
  receive: (
    accessToken: string,
    id: string,
    lines: { line_id: string; quantity: number }[],
    notes?: string
  ) =>
    apiRequest<BackendPurchaseOrder>(`/purchase-orders/${id}/receive`, {
      method: "POST",
      body: { lines, notes },
      accessToken,
    }),
};
