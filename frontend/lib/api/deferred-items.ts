// Typed REAL-mode client for the backend Deferred Item / MEL endpoints
// (backend/app/api/v1/deferred_items.py). organization_id is never sent by
// the client — the backend derives it from the authenticated JWT. Field
// names and types mirror backend/app/schemas/deferred_item.py exactly; no
// derived/aggregate fields exist here that the backend does not send.

import { apiRequest } from "@/lib/apiClient";

export interface BackendDeferredItem {
  id: string;
  organization_id: string;
  aircraft_id: string;
  work_order_id: string | null;
  mel_reference: string | null;
  category: string;
  description: string;
  opened_at: string;
  due_at: string | null;
  status: string;
  deferral_basis: string;
  operational_limitations: string | null;
  required_actions: string | null;
  approval_required: boolean;
  approval_status: string;
  closed_at: string | null;
  closure_notes: string | null;
}

export interface DeferredItemUpdateRequest {
  mel_reference?: string | null;
  category?: string | null;
  due_at?: string | null;
  deferral_basis?: string | null;
  operational_limitations?: string | null;
  required_actions?: string | null;
  approval_status?: string | null;
}

export interface DeferredItemCloseRequest {
  closed_at: string;
  closure_notes?: string | null;
}

export const deferredItemsApi = {
  listForFleet: (accessToken: string, openOnly = false) =>
    apiRequest<BackendDeferredItem[]>(`/fleet/deferred-items${openOnly ? "?open_only=true" : ""}`, {
      accessToken,
    }),

  listForAircraft: (accessToken: string, aircraftId: string, openOnly = false) =>
    apiRequest<BackendDeferredItem[]>(
      `/aircraft/${aircraftId}/deferred-items${openOnly ? "?open_only=true" : ""}`,
      { accessToken }
    ),

  get: (accessToken: string, itemId: string) =>
    apiRequest<BackendDeferredItem>(`/deferred-items/${itemId}`, { accessToken }),

  update: (accessToken: string, itemId: string, payload: DeferredItemUpdateRequest) =>
    apiRequest<BackendDeferredItem>(`/deferred-items/${itemId}`, {
      method: "PATCH",
      body: payload,
      accessToken,
    }),

  close: (accessToken: string, itemId: string, payload: DeferredItemCloseRequest) =>
    apiRequest<BackendDeferredItem>(`/deferred-items/${itemId}/close`, {
      method: "POST",
      body: payload,
      accessToken,
    }),
};
