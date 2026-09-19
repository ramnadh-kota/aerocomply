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

  inviteOrganizationAdmin: (
    accessToken: string,
    organizationId: string,
    payload: { email: string; full_name: string }
  ) =>
    apiRequest<{
      id: string;
      email: string;
      full_name: string;
      onboarding_email_sent: boolean;
    }>(`/platform/organizations/${organizationId}/invite-admin`, {
      method: "POST",
      body: payload,
      accessToken,
    }),

  provisionOrganization: (accessToken: string, payload: ProvisionOrganizationRequest) =>
    apiRequest<ProvisionOrganizationResponse>("/platform/organizations/provision", {
      method: "POST",
      body: payload,
      accessToken,
    }),

  resendAdminInvitation: (accessToken: string, userId: string) =>
    apiRequest<{ message: string }>(`/platform/admins/${userId}/resend-invitation`, {
      method: "POST",
      accessToken,
    }),

  revokeAdminInvitation: (accessToken: string, userId: string) =>
    apiRequest<{ message: string }>(`/platform/admins/${userId}/revoke-invitation`, {
      method: "POST",
      accessToken,
    }),
};

export interface ProvisionOrganizationRequest {
  organization_name: string;
  plan_id: string;
  subscription_status: "TRIALING" | "ACTIVE";
  admin_email: string;
  admin_full_name: string;
}

export interface ProvisionOrganizationResponse {
  organization_id: string;
  organization_name: string;
  organization_status: string;
  plan_id: string;
  subscription_id: string;
  subscription_status: string;
  admin_user_id: string;
  admin_email: string;
  admin_email_verified: boolean;
  onboarding_email_sent: boolean;
}
