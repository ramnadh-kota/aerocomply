// Typed REAL-mode client for platform plan/plan-feature administration
// (backend/app/api/v1/platform.py, M5). Requires PLATFORM_MANAGE on the
// backend — a non-platform-admin user calling these gets a 403 regardless of
// what the frontend shows. This client is intentionally thin: it only maps
// HTTP requests/responses to typed shapes. All validation/audit/transaction
// behavior lives in app.services.plan_service (M5) — nothing here duplicates it.

import { apiRequest } from "@/lib/apiClient";

export interface PlanResponse {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
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
}

export interface PlanUpdateRequest {
  name?: string;
  code?: string;
  description?: string | null;
}

export interface PlanFeatureCreateRequest {
  feature_key: string;
  enabled?: boolean;
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

  setPlanFeatureEnabled: (accessToken: string, planId: string, featureKey: string, enabled: boolean) =>
    apiRequest<PlanFeatureResponse>(`/platform/plans/${planId}/features/${encodeURIComponent(featureKey)}`, {
      method: "PATCH",
      body: { enabled },
      accessToken,
    }),
};
