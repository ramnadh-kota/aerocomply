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
};
