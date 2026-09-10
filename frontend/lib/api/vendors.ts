// Typed REAL-mode client for the backend Vendor endpoints
// (backend/app/api/v1/vendors.py). organization_id is never sent — the
// backend derives it from the authenticated JWT.

import { apiRequest } from "@/lib/apiClient";

export interface BackendVendor {
  id: string;
  organization_id: string;
  name: string;
  contact_email: string | null;
  location: string | null;
  certifications: string | null;
  approved: boolean;
  reliability_score: number | null;
  created_at: string;
}

export const vendorsApi = {
  list: (accessToken: string) => apiRequest<BackendVendor[]>("/vendors", { accessToken }),
};
