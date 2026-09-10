// Typed REAL-mode client for the backend inventory transaction endpoints
// (backend/app/api/v1/inventory.py). organization_id is never sent — the
// backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";
import type { BackendPart } from "@/lib/api/parts";

export interface InventoryTransactionResponse {
  id: string;
  organization_id: string;
  part_id: string;
  transaction_type: string;
  on_hand_delta: number;
  reserved_delta: number;
  quarantined_delta: number;
  reference_type: string | null;
  reference_id: string | null;
  notes: string | null;
  actor_user_id: string | null;
  created_at: string;
}

export const inventoryApi = {
  reserve: (accessToken: string, partId: string, quantity: number, notes?: string) =>
    apiRequest<InventoryTransactionResponse>(`/parts/${partId}/inventory/reserve`, {
      method: "POST",
      body: { quantity, notes },
      accessToken,
    }),
  release: (accessToken: string, partId: string, quantity: number, notes?: string) =>
    apiRequest<InventoryTransactionResponse>(`/parts/${partId}/inventory/release`, {
      method: "POST",
      body: { quantity, notes },
      accessToken,
    }),
  consume: (accessToken: string, partId: string, quantity: number, notes?: string) =>
    apiRequest<InventoryTransactionResponse>(`/parts/${partId}/inventory/consume`, {
      method: "POST",
      body: { quantity, notes },
      accessToken,
    }),
  quarantine: (accessToken: string, partId: string, quantity: number, reason: string) =>
    apiRequest<InventoryTransactionResponse>(`/parts/${partId}/inventory/quarantine`, {
      method: "POST",
      body: { quantity, reason },
      accessToken,
    }),
  releaseQuarantine: (
    accessToken: string,
    partId: string,
    quantity: number,
    newStatus: "SERVICEABLE" | "UNSERVICEABLE" | "SCRAPPED",
    notes?: string
  ) =>
    apiRequest<InventoryTransactionResponse>(`/parts/${partId}/inventory/release-quarantine`, {
      method: "POST",
      body: { quantity, new_status: newStatus, notes },
      accessToken,
    }),
};

export type { BackendPart };
