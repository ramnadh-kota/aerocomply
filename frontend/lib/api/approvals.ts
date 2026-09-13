// Typed REAL-mode client for the M14 platform governance approval API
// (backend/app/api/v1/platform.py GET/POST /platform/approvals*). Requires
// PLATFORM_MANAGE on the backend for every call, plus
// PLATFORM_ENTITLEMENT_OVERRIDE specifically to approve (enforced server-
// side inside approval_service.approve_approval_request -- never re-derived
// here). This is a thin client: it never decides whether a request is
// expansive, never re-implements a state transition, and never claims a
// stronger governance guarantee (e.g. "two-person approval") than the
// backend actually provides -- see approval_service.py's module docstring
// on self-approval.

import { apiRequest } from "@/lib/apiClient";

export type ApprovalRequestType = "feature_override_expansion" | "usage_limit_expansion";
export type ApprovalStatus = "PENDING" | "APPROVED" | "REJECTED" | "CANCELED";

export interface ApprovalRequestResponse {
  id: string;
  organization_id: string;
  request_type: ApprovalRequestType;
  status: ApprovalStatus;
  feature_key: string;
  requested_enabled: boolean | null;
  limit_key: string | null;
  requested_limit_value: number | null;
  requested_is_unlimited: boolean | null;
  reason: string | null;
  requested_by_user_id: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  decision_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalRequestListResponse {
  items: ApprovalRequestResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApprovalListParams {
  status?: ApprovalStatus;
  organization_id?: string;
  limit?: number;
  offset?: number;
}

export interface CreateFeatureOverrideApprovalParams {
  feature_key: string;
  requested_enabled: true;
  reason?: string;
}

export interface CreateUsageLimitApprovalParams {
  feature_key: string;
  limit_key: string;
  requested_limit_value?: number;
  requested_is_unlimited?: boolean;
  reason?: string;
}

export const approvalsApi = {
  listApprovals: (accessToken: string, params: ApprovalListParams = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.organization_id) query.set("organization_id", params.organization_id);
    if (params.limit !== undefined) query.set("limit", String(params.limit));
    if (params.offset !== undefined) query.set("offset", String(params.offset));
    const qs = query.toString();
    return apiRequest<ApprovalRequestListResponse>(`/platform/approvals${qs ? `?${qs}` : ""}`, {
      accessToken,
    });
  },

  getApproval: (accessToken: string, approvalId: string) =>
    apiRequest<ApprovalRequestResponse>(`/platform/approvals/${approvalId}`, { accessToken }),

  createFeatureOverrideRequest: (
    accessToken: string,
    organizationId: string,
    params: CreateFeatureOverrideApprovalParams
  ) =>
    apiRequest<ApprovalRequestResponse>(`/platform/organizations/${organizationId}/approvals`, {
      method: "POST",
      accessToken,
      body: { request_type: "feature_override_expansion", ...params },
    }),

  createUsageLimitRequest: (
    accessToken: string,
    organizationId: string,
    params: CreateUsageLimitApprovalParams
  ) =>
    apiRequest<ApprovalRequestResponse>(`/platform/organizations/${organizationId}/approvals`, {
      method: "POST",
      accessToken,
      body: { request_type: "usage_limit_expansion", ...params },
    }),

  approve: (accessToken: string, approvalId: string, decisionReason?: string) =>
    apiRequest<ApprovalRequestResponse>(`/platform/approvals/${approvalId}/approve`, {
      method: "POST",
      accessToken,
      body: { decision_reason: decisionReason },
    }),

  reject: (accessToken: string, approvalId: string, decisionReason?: string) =>
    apiRequest<ApprovalRequestResponse>(`/platform/approvals/${approvalId}/reject`, {
      method: "POST",
      accessToken,
      body: { decision_reason: decisionReason },
    }),

  cancel: (accessToken: string, approvalId: string) =>
    apiRequest<ApprovalRequestResponse>(`/platform/approvals/${approvalId}/cancel`, {
      method: "POST",
      accessToken,
    }),
};
