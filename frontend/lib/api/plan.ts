// Typed REAL-mode client for platform plan/plan-feature administration
// (backend/app/api/v1/platform.py, M5). Requires PLATFORM_MANAGE on the
// backend — a non-platform-admin user calling these gets a 403 regardless of
// what the frontend shows. This client is intentionally thin: it only maps
// HTTP requests/responses to typed shapes. All validation/audit/transaction
// behavior lives in app.services.plan_service (M5) — nothing here duplicates it.

import { apiRequest } from "@/lib/apiClient";
import type { AuditEventResponse } from "@/lib/api/audit";

export interface PlanResponse {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
  suite_id?: string | null;
  asset_scope?: string | null;
  included_features_count?: number;
  tenant_count?: number;
  created_at: string;
  updated_at: string;
}

export interface PlanFeatureResponse {
  id: string;
  plan_id: string;
  feature_key: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface PlanCreateRequest {
  name: string;
  code: string;
  description?: string | null;
  is_active?: boolean;
  suite_id?: string | null;
  asset_scope?: string | null;
}

export interface PlanUpdateRequest {
  name?: string;
  code?: string;
  description?: string | null;
  suite_id?: string | null;
  asset_scope?: string | null;
}

export interface PlanFeatureCreateRequest {
  feature_key: string;
  enabled?: boolean;
}

export interface PlanFeatureBulkItem {
  feature_key: string;
  enabled: boolean;
}

export interface PlanSubscribedTenantResponse {
  organization_id: string;
  organization_name: string;
  organization_status: string;
  subscription_id: string;
  subscription_status: string;
  starts_at: string;
  ends_at: string | null;
}

export interface PlanLimitItem {
  limit_key: string;
  limit_value: number | null;
  is_unlimited: boolean;
}

export interface PlanLimitResponse {
  id: string;
  plan_id: string;
  limit_key: string;
  limit_value: number | null;
  is_unlimited: boolean;
  created_at: string;
  updated_at: string;
}

export const planApi = {
  listPlans: (accessToken: string) => apiRequest<PlanResponse[]>("/platform/plans", { accessToken }),

  createPlan: (accessToken: string, payload: PlanCreateRequest) =>
    apiRequest<PlanResponse>("/platform/plans", { method: "POST", body: payload, accessToken }),

  getPlan: (accessToken: string, planId: string) =>
    apiRequest<PlanResponse>(`/platform/plans/${planId}`, { accessToken }),

  updatePlan: (accessToken: string, planId: string, payload: PlanUpdateRequest) =>
    apiRequest<PlanResponse>(`/platform/plans/${planId}`, { method: "PATCH", body: payload, accessToken }),

  activatePlan: (accessToken: string, planId: string) =>
    apiRequest<PlanResponse>(`/platform/plans/${planId}/activate`, { method: "POST", accessToken }),

  deactivatePlan: (accessToken: string, planId: string) =>
    apiRequest<PlanResponse>(`/platform/plans/${planId}/deactivate`, { method: "POST", accessToken }),

  listPlanFeatures: (accessToken: string, planId: string) =>
    apiRequest<PlanFeatureResponse[]>(`/platform/plans/${planId}/features`, { accessToken }),

  createPlanFeature: (accessToken: string, planId: string, payload: PlanFeatureCreateRequest) =>
    apiRequest<PlanFeatureResponse>(`/platform/plans/${planId}/features`, {
      method: "POST",
      body: payload,
      accessToken,
    }),

  bulkSetPlanFeatures: (accessToken: string, planId: string, features: PlanFeatureBulkItem[]) =>
    apiRequest<PlanFeatureResponse[]>(`/platform/plans/${planId}/features`, {
      method: "PUT",
      body: { features },
      accessToken,
    }),

  setPlanFeatureEnabled: (accessToken: string, planId: string, featureKey: string, enabled: boolean) =>
    apiRequest<PlanFeatureResponse>(`/platform/plans/${planId}/features/${encodeURIComponent(featureKey)}`, {
      method: "PATCH",
      body: { enabled },
      accessToken,
    }),

  listPlanLimits: (accessToken: string, planId: string) =>
    apiRequest<PlanLimitResponse[]>(`/platform/plans/${planId}/limits`, { accessToken }),

  bulkSetPlanLimits: (accessToken: string, planId: string, limits: PlanLimitItem[]) =>
    apiRequest<PlanLimitResponse[]>(`/platform/plans/${planId}/limits`, {
      method: "PUT",
      body: { limits },
      accessToken,
    }),

  listPlanTenants: (accessToken: string, planId: string) =>
    apiRequest<PlanSubscribedTenantResponse[]>(`/platform/plans/${planId}/tenants`, { accessToken }),

  getPlanAuditTrail: (accessToken: string, planId: string) =>
    apiRequest<AuditEventResponse[]>(`/platform/plans/${planId}/audit-trail`, { accessToken }),
};

