// Typed REAL-mode client for platform-level (cross-tenant) administration
// (backend/app/api/v1/platform.py). Requires the PLATFORM_MANAGE permission
// on the backend — a customer organization admin calling these gets a 403
// regardless of what the frontend shows.

import { apiRequest } from "@/lib/apiClient";

export interface BackendPlatformOrganization {
  id: string;
  name: string;
  status: "ACTIVE" | "SUSPENDED";
  created_at: string;
  user_count: number;
  aircraft_count: number;
}

export const platformApi = {
  listOrganizations: (accessToken: string) =>
    apiRequest<BackendPlatformOrganization[]>("/platform/organizations", { accessToken }),

  createOrganization: (accessToken: string, name: string) =>
    apiRequest<BackendPlatformOrganization>("/platform/organizations", {
      method: "POST",
      body: { name },
      accessToken,
    }),

  getOrganization: (accessToken: string, id: string) =>
    apiRequest<BackendPlatformOrganization>(`/platform/organizations/${id}`, { accessToken }),

  activateOrganization: (accessToken: string, id: string) =>
    apiRequest<BackendPlatformOrganization>(`/platform/organizations/${id}/activate`, {
      method: "POST",
      accessToken,
    }),

  suspendOrganization: (accessToken: string, id: string) =>
    apiRequest<BackendPlatformOrganization>(`/platform/organizations/${id}/suspend`, {
      method: "POST",
      accessToken,
    }),

  createOrganizationAdmin: (
    accessToken: string,
    organizationId: string,
    payload: { email: string; full_name: string; password: string }
  ) =>
    apiRequest<{ id: string; email: string; full_name: string }>(
      `/platform/organizations/${organizationId}/admins`,
      { method: "POST", body: payload, accessToken }
    ),
};
