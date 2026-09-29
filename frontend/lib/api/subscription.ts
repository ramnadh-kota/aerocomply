// Typed REAL-mode client for platform subscription administration
// (backend/app/api/v1/platform.py, M6). Requires PLATFORM_MANAGE on the
// backend — a non-platform-admin user calling these gets a 403 regardless of
// what the frontend shows. This client is intentionally thin: it only maps
// HTTP requests/responses to typed shapes. All lifecycle/eligibility/
// ambiguity rules live in app.services.subscription_service (M6) — nothing
// here duplicates them. In particular, this file never decides which
// subscription is "current" for an organization; that is the M2 resolver's
// job (see lib/api/entitlement.ts), and the Subscription Administration UI
// only ever displays raw status/date fields returned here.

import { apiRequest } from "@/lib/apiClient";

// Mirrors app/models/subscription.py's SubscriptionStatus values exactly.
export type SubscriptionStatus = "TRIALING" | "ACTIVE" | "PAST_DUE" | "CANCELED" | "SCHEDULED";

export interface ProductSuiteResponse {
  id: string;
  code: string;
  name: string;
  description: string | null;
  icon?: string | null;
  display_order: number;
  is_active: boolean;
  plans_count?: number;
  modules_count?: number;
  features_count?: number;
  organizations_count?: number;
  active_subscriptions_count?: number;
  created_at: string;
  updated_at: string;
}

export interface PlanResponse {
  id: string;
  name: string;
  code: string;
  description: string | null;
  is_active: boolean;
  suite_id?: string | null;
  suite_code?: string | null;
  suite_name?: string | null;
  asset_scope?: string | null;
  included_features_count: number;
  tenant_count: number;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionResponse {
  id: string;
  organization_id: string;
  plan_id: string;
  suite_id?: string | null;
  status: SubscriptionStatus | string;
  starts_at: string;
  ends_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionCreateRequest {
  plan_id: string;
  suite_id?: string | null;
  status: string;
  starts_at: string;
  ends_at?: string | null;
}

export interface SubscriptionScheduleRequest {
  plan_id: string;
  suite_id?: string | null;
  starts_at: string;
  ends_at?: string | null;
}

export interface SubscriptionUpdateRequest {
  status?: string;
  plan_id?: string;
  suite_id?: string | null;
  starts_at?: string;
  ends_at?: string | null;
}

export const subscriptionApi = {
  listForOrganization: (accessToken: string, organizationId: string) =>
    apiRequest<SubscriptionResponse[]>(`/platform/organizations/${organizationId}/subscriptions`, {
      accessToken,
    }),

  create: (accessToken: string, organizationId: string, payload: SubscriptionCreateRequest) =>
    apiRequest<SubscriptionResponse>(`/platform/organizations/${organizationId}/subscriptions`, {
      method: "POST",
      body: payload,
      accessToken,
    }),

  schedule: (accessToken: string, organizationId: string, payload: SubscriptionScheduleRequest) =>
    apiRequest<SubscriptionResponse>(
      `/platform/organizations/${organizationId}/subscriptions/schedule`,
      { method: "POST", body: payload, accessToken }
    ),

  get: (accessToken: string, subscriptionId: string) =>
    apiRequest<SubscriptionResponse>(`/platform/subscriptions/${subscriptionId}`, { accessToken }),

  update: (accessToken: string, subscriptionId: string, payload: SubscriptionUpdateRequest) =>
    apiRequest<SubscriptionResponse>(`/platform/subscriptions/${subscriptionId}`, {
      method: "PATCH",
      body: payload,
      accessToken,
    }),

  cancel: (accessToken: string, subscriptionId: string) =>
    apiRequest<SubscriptionResponse>(`/platform/subscriptions/${subscriptionId}/cancel`, {
      method: "POST",
      accessToken,
    }),
};

/**
 * Lifecycle transition table — a verbatim mirror of `_ALLOWED_TRANSITIONS`
 * in backend/app/services/subscription_service.py. Used ONLY to decide which
 * buttons to offer; the backend remains the authority and rejects anything
 * invalid with a 409 that the UI surfaces as-is.
 */
export const ALLOWED_TRANSITIONS: Record<string, SubscriptionStatus[]> = {
  TRIALING: ["ACTIVE", "PAST_DUE", "CANCELED"],
  ACTIVE: ["PAST_DUE", "CANCELED"],
  PAST_DUE: ["ACTIVE", "CANCELED"],
  SCHEDULED: ["TRIALING", "ACTIVE", "CANCELED"],
  CANCELED: [],
};

/** Statuses offered when creating a subscription from the admin UI. */
export const CREATABLE_STATUSES: SubscriptionStatus[] = [
  "TRIALING",
  "ACTIVE",
  "PAST_DUE",
  "SCHEDULED",
];

export const CURRENT_GRANTING_STATUSES: ReadonlySet<string> = new Set([
  "TRIALING",
  "ACTIVE",
  "PAST_DUE",
]);

/**
 * Categorize a subscription record into Current, Upcoming, or Historical
 * based on its status and date range relative to `now`.
 */
export function groupSubscription(
  sub: Pick<SubscriptionResponse, "status" | "starts_at" | "ends_at">,
  now: Date = new Date()
): "Current" | "Upcoming" | "Historical" {
  if (sub.status === "CANCELED") return "Historical";
  if (sub.status === "SCHEDULED") return "Upcoming";
  if (!CURRENT_GRANTING_STATUSES.has(sub.status)) return "Historical";
  const starts = new Date(sub.starts_at);
  const ends = sub.ends_at ? new Date(sub.ends_at) : null;
  if (starts.getTime() > now.getTime()) return "Upcoming";
  if (ends && ends.getTime() <= now.getTime()) return "Historical";
  return "Current";
}
