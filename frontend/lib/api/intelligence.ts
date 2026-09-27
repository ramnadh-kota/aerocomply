// Typed REAL-mode client for the backend D2.2 Intelligence endpoints
// (backend/app/api/v1/intelligence.py). organization_id is never sent --
// the backend derives it from the authenticated JWT (same convention as
// every other lib/api/*.ts client).
//
// These types mirror backend/app/schemas/intelligence.py field-for-field.
// This file must never reproduce the backend's readiness/risk/priority/
// decision/recommendation LOGIC in TypeScript -- it only types and fetches
// what the five deterministic endpoints already compute.

import { apiRequest } from "@/lib/apiClient";

export type IntelligenceReadinessState = "READY" | "BLOCKED" | "UNKNOWN";
export type IntelligenceRiskLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN";
// Priority reuses the exact risk tier vocabulary (see backend
// app/schemas/intelligence.py: PriorityLevel = RiskLevel) -- not a second scale.
export type IntelligencePriorityLevel = IntelligenceRiskLevel;
export type IntelligenceDecisionState =
  | "INSUFFICIENT_DATA"
  | "IMMEDIATE_ACTION_REQUIRED"
  | "ACTION_REQUIRED"
  | "MONITOR"
  | "NO_ACTION_REQUIRED";
export type IntelligenceKleeneValue = "TRUE" | "FALSE" | "UNKNOWN";
export type IntelligenceBlockerSourceDomain = "AEROSPACE_STATE" | "WORK_ORDER" | "DEPLOYMENT";
export type IntelligenceRecommendationActionCategory =
  | "OBTAIN_MISSING_INFORMATION"
  | "PERFORM_REQUIRED_ACTION"
  | "RESOLVE_BLOCKER"
  | "MONITOR_CONDITION"
  | "NO_ACTION_REQUIRED";

export interface IntelligenceBlocker {
  source_domain: IntelligenceBlockerSourceDomain;
  category: string;
  description: string;
  related_record_id: string | null;
  related_record_type: string | null;
  required_action: string | null;
  resolution_action: string | null;
  regulatory_reference: string | null;
}

export interface IntelligenceWarningRef {
  warning_id: string;
  category: string;
  dimension: string;
  message: string;
  source_type: string | null;
  source_id: string | null;
  source_label: string | null;
}

export interface AssetReadinessIntelligence {
  asset_id: string;
  aircraft_id: string | null;
  operational_state: string;
  readiness_state: IntelligenceReadinessState;
  blockers: IntelligenceBlocker[];
  contributing_factors: Record<string, number | string>;
  explanation: string[];
  data_completeness: string;
  evaluated_at: string;
}

export interface IntelligenceRiskFactor {
  name: string;
  value: IntelligenceKleeneValue;
  explanation: string;
}

export interface AssetRiskIntelligence {
  asset_id: string;
  risk_level: IntelligenceRiskLevel;
  readiness_state: IntelligenceReadinessState;
  factors: IntelligenceRiskFactor[];
  contributing_counts: Record<string, number>;
  explanation: string[];
  evaluated_at: string;
}

export interface AssetPriorityIntelligence {
  asset_id: string;
  aircraft_id: string | null;
  priority_level: IntelligencePriorityLevel;
  risk_level: IntelligenceRiskLevel;
  readiness_state: IntelligenceReadinessState;
  escalated: boolean;
  blocker_count: number;
  distinct_blocker_domains: number;
  warning_count: number;
  blockers: IntelligenceBlocker[];
  warnings: IntelligenceWarningRef[];
  explanation: string[];
  evaluated_at: string;
}

export interface AssetDecision {
  asset_id: string;
  aircraft_id: string | null;
  decision_state: IntelligenceDecisionState;
  decision_reason: string;
  priority_level: IntelligencePriorityLevel;
  risk_level: IntelligenceRiskLevel;
  readiness_state: IntelligenceReadinessState;
  required_information: string[];
  blockers: IntelligenceBlocker[];
  warnings: IntelligenceWarningRef[];
  explanation: string[];
  evaluated_at: string;
}

export interface IntelligenceRecommendationItem {
  action_category: IntelligenceRecommendationActionCategory;
  action: string;
  resolution_condition: string | null;
  source_blocker: IntelligenceBlocker | null;
}

export interface AssetRecommendation {
  asset_id: string;
  aircraft_id: string | null;
  recommendation_state: IntelligenceDecisionState;
  priority_level: IntelligencePriorityLevel;
  risk_level: IntelligenceRiskLevel;
  readiness_state: IntelligenceReadinessState;
  items: IntelligenceRecommendationItem[];
  required_information: string[];
  blockers: IntelligenceBlocker[];
  warnings: IntelligenceWarningRef[];
  explanation: string[];
  evaluated_at: string;
}

export interface FleetAssetIntelligence {
  asset_id: string;
  registration: string | null;
  asset_type: string;
  operational_state: string;
  aerospace_intelligence_status: string;
  readiness_state: IntelligenceReadinessState;
  risk_level: IntelligenceRiskLevel;
  priority_level: IntelligencePriorityLevel;
  decision_state: IntelligenceDecisionState;
  decision_reason: string;
  top_recommendation_action: string | null;
  blocker_count: number;
  warning_count: number;
  blockers: IntelligenceBlocker[];
  warnings: IntelligenceWarningRef[];
  evaluated_at: string;
}

export interface FleetIntelligenceSummary {
  total_assets: number;
  assets: FleetAssetIntelligence[];
  evaluated_at: string;
}

export const intelligenceApi = {
  getFleet: (accessToken: string) =>
    apiRequest<FleetIntelligenceSummary>("/intelligence/fleet", { accessToken }),

  getReadiness: (accessToken: string, assetId: string) =>
    apiRequest<AssetReadinessIntelligence>(`/intelligence/assets/${assetId}/readiness`, { accessToken }),

  getRisk: (accessToken: string, assetId: string) =>
    apiRequest<AssetRiskIntelligence>(`/intelligence/assets/${assetId}/risk`, { accessToken }),

  getPriority: (accessToken: string, assetId: string) =>
    apiRequest<AssetPriorityIntelligence>(`/intelligence/assets/${assetId}/priority`, { accessToken }),

  getDecision: (accessToken: string, assetId: string) =>
    apiRequest<AssetDecision>(`/intelligence/assets/${assetId}/decision`, { accessToken }),

  getRecommendations: (accessToken: string, assetId: string) =>
    apiRequest<AssetRecommendation>(`/intelligence/assets/${assetId}/recommendations`, { accessToken }),
};
