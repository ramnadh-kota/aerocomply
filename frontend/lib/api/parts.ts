// Typed REAL-mode client for the backend Part endpoints
// (backend/app/api/v1/parts.py). organization_id is never sent — the
// backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendPart {
  id: string;
  organization_id: string;
  part_number: string;
  description: string;
  manufacturer: string | null;
  condition: string | null;
  serial_number: string | null;
  batch_or_lot: string | null;
  location: string | null;
  serviceability_status: string;
  quarantine_reason: string | null;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_quarantined: number;
  available_quantity: number;
  created_at: string;
}

export const partsApi = {
  list: (accessToken: string) => apiRequest<BackendPart[]>("/parts", { accessToken }),
};
