import { apiRequest } from "@/lib/apiClient";
import type { AuditEventResponse } from "@/lib/api/audit";

export interface TenantProfile {
  id: string;
  name: string;
  status: string;
  industry: string | null;
  created_at: string;
  primary_contact_email: string | null;
  primary_contact_name: string | null;
}

export interface TenantProfileUpdatePayload {
  name?: string;
  industry?: string;
}

export interface TenantSettings {
  organization_id: string;
  timezone: string;
  operational_mode: string;
  default_asset_type: string;
  notification_email: string | null;
}

export interface TenantSettingsUpdatePayload {
  timezone?: string;
  operational_mode?: string;
  default_asset_type?: string;
  notification_email?: string;
}

export interface TenantUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  created_at: string;
}

export interface TenantRoleInfo {
  role_name: string;
  display_name: string;
  description: string;
  permissions: string[];
  is_system_role: boolean;
}

export interface TenantInvitation {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: "PENDING" | "ACCEPTED" | "EXPIRED" | "CANCELLED";
  created_at: string;
  expires_at: string;
  can_resend: boolean;
  can_cancel: boolean;
}

export interface TenantInvitationPayload {
  email: string;
  full_name: string;
  role: string;
}

export interface TenantTeamMember {
  user_id: string;
  full_name: string;
  email: string;
  role: string;
}

export interface TenantTeam {
  id: string;
  name: string;
  description: string;
  lead_role: string;
  member_count: number;
  members: TenantTeamMember[];
}

export interface TenantUsageMetric {
  key: string;
  label: string;
  tracked: boolean;
  value: number | null;
  limit: number | null;
  is_unlimited: boolean;
  unit: string;
  status: "TRACKED" | "NOT_TRACKED" | "AT_RISK" | "EXCEEDED";
}

export interface TenantUsage {
  organization_id: string;
  metrics: TenantUsageMetric[];
}

export interface TenantDashboardAttentionItem {
  severity: "INFO" | "WARNING" | "CRITICAL";
  category: string;
  title: string;
  message: string;
  link_href?: string;
  link_label?: string;
}

export interface TenantDashboardStats {
  organization: TenantProfile;
  users_count: number;
  active_users_count: number;
  pending_invitations_count: number;
  fleet_count: number;
  aircraft_count: number;
  drone_count: number;
  facility_count: number;
  team_count: number;
  current_plan: string | null;
  subscription_status: string | null;
  effective_features_count: number;
  attention_items: TenantDashboardAttentionItem[];
}

export const tenantApi = {
  getDashboard: (accessToken: string) =>
    apiRequest<TenantDashboardStats>("/tenant/dashboard", { accessToken }),

  getProfile: (accessToken: string) =>
    apiRequest<TenantProfile>("/tenant/profile", { accessToken }),

  updateProfile: (accessToken: string, payload: TenantProfileUpdatePayload) =>
    apiRequest<TenantProfile>("/tenant/profile", {
      accessToken,
      method: "PATCH",
      body: payload,
    }),

  getSettings: (accessToken: string) =>
    apiRequest<TenantSettings>("/tenant/settings", { accessToken }),

  updateSettings: (accessToken: string, payload: TenantSettingsUpdatePayload) =>
    apiRequest<TenantSettings>("/tenant/settings", {
      accessToken,
      method: "PATCH",
      body: payload,
    }),

  // Platform Control Plane: soft-deletes this admin's OWN organization
  // (backend/app/services/deletion_service.py's request_organization_
  // deletion). There is no tenant-facing undo -- every subsequent request,
  // including this admin's own current session, is refused immediately
  // afterward. Only Platform Admin can restore or approve permanent
  // deletion (lib/api/deletion.ts).
  requestDeletion: (accessToken: string, reason?: string) =>
    apiRequest<{ message: string }>("/tenant/deletion-request", {
      accessToken,
      method: "POST",
      body: { reason },
    }),

  listUsers: (accessToken: string) =>
    apiRequest<TenantUser[]>("/tenant/users", { accessToken }),

  getUser: (accessToken: string, userId: string) =>
    apiRequest<TenantUser>(`/tenant/users/${userId}`, { accessToken }),

  updateUserRoles: (accessToken: string, userId: string, roles: string[]) =>
    apiRequest<TenantUser>(`/tenant/users/${userId}/roles`, {
      accessToken,
      method: "PATCH",
      body: { roles },
    }),

  updateUserStatus: (accessToken: string, userId: string, isActive: boolean) =>
    apiRequest<TenantUser>(`/tenant/users/${userId}/status`, {
      accessToken,
      method: "PATCH",
      body: { is_active: isActive },
    }),

  listRoles: (accessToken: string) =>
    apiRequest<TenantRoleInfo[]>("/tenant/roles", { accessToken }),

  listInvitations: (accessToken: string) =>
    apiRequest<TenantInvitation[]>("/tenant/invitations", { accessToken }),

  inviteUser: (accessToken: string, payload: TenantInvitationPayload) =>
    apiRequest<TenantInvitation>("/tenant/invitations", {
      accessToken,
      method: "POST",
      body: payload,
    }),

  resendInvitation: (accessToken: string, userId: string) =>
    apiRequest<{ message: string }>(`/tenant/invitations/${userId}/resend`, {
      accessToken,
      method: "POST",
    }),

  cancelInvitation: (accessToken: string, userId: string) =>
    apiRequest<{ message: string }>(`/tenant/invitations/${userId}/cancel`, {
      accessToken,
      method: "POST",
    }),

  listTeams: (accessToken: string) =>
    apiRequest<TenantTeam[]>("/tenant/teams", { accessToken }),

  getUsage: (accessToken: string) =>
    apiRequest<TenantUsage>("/tenant/usage", { accessToken }),

  listAuditEvents: (
    accessToken: string,
    params: { limit?: number; offset?: number } = {}
  ) => {
    const qs = new URLSearchParams();
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return apiRequest<AuditEventResponse[]>(
      `/tenant/audit${query ? `?${query}` : ""}`,
      { accessToken }
    );
  },
};
