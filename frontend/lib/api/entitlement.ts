// Typed REAL-mode client for platform entitlement/override read endpoints
// (backend/app/api/v1/platform.py, M3 + M6). Requires PLATFORM_MANAGE on the
// backend — a customer/org-admin user calling these gets a 403 regardless of
// what the frontend shows. This client is intentionally thin: it only maps
// HTTP responses to typed shapes. All entitlement resolution logic lives in
// app.services.entitlement_service (M2) — nothing here recomputes it.

import { apiRequest } from "@/lib/apiClient";

export interface UsageLimitConfiguration {
  feature_key: string;
  limit_key: string;
  limit_value: number | null;
  is_unlimited: boolean;
}

export type ResolutionStatus =
  | "ACTIVE"
  | "INACTIVE_PLAN"
  | "SUSPENDED"
  | "NO_SUBSCRIPTION"
  | "AMBIGUOUS"
  | "INVALID";

export interface EntitlementResolutionResponse {
  organization_id: string;
  resolution_status: ResolutionStatus | string;
  organization_status: string;
  subscription_id: string | null;
  subscription_status: string | null;
  plan_id: string | null;
  plan_code: string | null;
  plan_name: string | null;
  effective_features: Record<string, boolean>;
  usage_limits: UsageLimitConfiguration[];
  reason: string;
}

export interface TenantFeatureOverrideResponse {
  id: string;
  organization_id: string;
  feature_key: string;
  enabled: boolean;
  reason: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface TenantFeatureOverrideCreateRequest {
  feature_key: string;
  enabled: boolean;
  reason?: string | null;
  expires_at?: string | null;
}

export interface TenantFeatureOverrideUpdateRequest {
  enabled?: boolean | null;
  reason?: string | null;
  expires_at?: string | null;
}

export interface TenantUsageLimitResponse {
  id: string;
  organization_id: string;
  feature_key: string;
  limit_key: string;
  limit_value: number | null;
  is_unlimited: boolean;
  created_at: string;
  updated_at: string;
}

export interface TenantUsageLimitCreateRequest {
  feature_key: string;
  limit_key: string;
  limit_value?: number | null;
  is_unlimited?: boolean;
}

export interface TenantUsageLimitUpdateRequest {
  limit_value?: number | null;
  is_unlimited?: boolean | null;
}

export type ExpirationState = "PERMANENT" | "ACTIVE" | "EXPIRING_SOON" | "EXPIRED";

export function getOverrideExpirationState(
  override: TenantFeatureOverrideResponse,
  now: Date = new Date()
): { state: ExpirationState; label: string; isApplicable: boolean } {
  if (!override.expires_at) {
    return { state: "PERMANENT", label: "Permanent (No Expiry)", isApplicable: true };
  }
  const expires = new Date(override.expires_at);
  if (Number.isNaN(expires.getTime())) {
    return { state: "EXPIRED", label: "Invalid Expiration", isApplicable: false };
  }
  const diffMs = expires.getTime() - now.getTime();
  if (diffMs <= 0) {
    return { state: "EXPIRED", label: "Expired", isApplicable: false };
  }
  if (diffMs <= 24 * 60 * 60 * 1000) {
    return { state: "EXPIRING_SOON", label: "Expires Soon", isApplicable: true };
  }
  return { state: "ACTIVE", label: "Active", isApplicable: true };
}

export const entitlementApi = {
  getEntitlements: (accessToken: string, organizationId: string) =>
    apiRequest<EntitlementResolutionResponse>(
      `/platform/organizations/${organizationId}/entitlements`,
      { accessToken }
    ),

  listFeatureOverrides: (accessToken: string, organizationId: string) =>
    apiRequest<TenantFeatureOverrideResponse[]>(
      `/platform/organizations/${organizationId}/feature-overrides`,
      { accessToken }
    ),

  createFeatureOverride: (
    accessToken: string,
    organizationId: string,
    payload: TenantFeatureOverrideCreateRequest
  ) =>
    apiRequest<TenantFeatureOverrideResponse>(
      `/platform/organizations/${organizationId}/feature-overrides`,
      {
        accessToken,
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  updateFeatureOverride: (
    accessToken: string,
    organizationId: string,
    featureKey: string,
    payload: TenantFeatureOverrideUpdateRequest
  ) =>
    apiRequest<TenantFeatureOverrideResponse>(
      `/platform/organizations/${organizationId}/feature-overrides/${encodeURIComponent(featureKey)}`,
      {
        accessToken,
        method: "PATCH",
        body: JSON.stringify(payload),
      }
    ),

  removeFeatureOverride: (accessToken: string, organizationId: string, featureKey: string) =>
    apiRequest<void>(
      `/platform/organizations/${organizationId}/feature-overrides/${encodeURIComponent(featureKey)}`,
      {
        accessToken,
        method: "DELETE",
      }
    ),

  listUsageLimits: (accessToken: string, organizationId: string) =>
    apiRequest<TenantUsageLimitResponse[]>(
      `/platform/organizations/${organizationId}/usage-limits`,
      { accessToken }
    ),

  createUsageLimit: (
    accessToken: string,
    organizationId: string,
    payload: TenantUsageLimitCreateRequest
  ) =>
    apiRequest<TenantUsageLimitResponse>(
      `/platform/organizations/${organizationId}/usage-limits`,
      {
        accessToken,
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  updateUsageLimit: (
    accessToken: string,
    organizationId: string,
    featureKey: string,
    limitKey: string,
    payload: TenantUsageLimitUpdateRequest
  ) =>
    apiRequest<TenantUsageLimitResponse>(
      `/platform/organizations/${organizationId}/usage-limits/${encodeURIComponent(featureKey)}/${encodeURIComponent(limitKey)}`,
      {
        accessToken,
        method: "PATCH",
        body: JSON.stringify(payload),
      }
    ),

  removeUsageLimit: (
    accessToken: string,
    organizationId: string,
    featureKey: string,
    limitKey: string
  ) =>
    apiRequest<void>(
      `/platform/organizations/${organizationId}/usage-limits/${encodeURIComponent(featureKey)}/${encodeURIComponent(limitKey)}`,
      {
        accessToken,
        method: "DELETE",
      }
    ),
};
