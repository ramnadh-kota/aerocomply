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

// ==========================================
// M7 PROACTIVE INTELLIGENCE CONTRACTS
// ==========================================

export type SignalType =
  | "THRESHOLD_PROXIMITY"
  | "BATTERY_HEALTH_DEGRADATION"
  | "BATTERY_CYCLE_EXHAUSTION"
  | "INSPECTION_INTERVAL_EARLY_WARNING"
  | "RECURRING_FINDING_PATTERN"
  | "UTILIZATION_PACE_ACCELERATION"
  | "COMPLIANCE_VERIFICATION_GAP"
  | "UNVERIFIED_COMPLIANCE_OBLIGATION"
  | "MISSING_WORK_ORDER_EVIDENCE"
  | "READINESS_DEGRADATION_EXPLAINER"
  | "FLEET_WIDE_DEFECT_PATTERN"
  | "SYSTEMIC_OVERDUE_PATTERN"
  | "RECURRING_DEFECT_CLUSTER";

export type SignalSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type SignalPriority = "IMMEDIATE" | "UPCOMING" | "WATCHLIST" | "INFORMATIONAL";
export type SignalStatus = "OPEN" | "ACKNOWLEDGED" | "IN_REVIEW" | "RESOLVED" | "DISMISSED";
export type SignalTrend = "WORSENING" | "STABLE" | "IMPROVING";

export interface SignalEvidenceRef {
  evidence_type: string;
  entity_id: string;
  entity_type: string;
  summary: string;
  url?: string | null;
  observed_value?: string | null;
  threshold_value?: string | null;
}

export interface SignalActionItem {
  action_type: string;
  description: string;
  target_route?: string | null;
  requires_authorization: boolean;
}

export interface ProactiveSignal {
  id: string;
  organization_id: string;
  asset_id: string | null;
  signal_type: SignalType;
  severity: SignalSeverity;
  priority: SignalPriority;
  status: SignalStatus;
  title: string;
  description: string;
  trigger_condition: string;
  evidence: SignalEvidenceRef[];
  recommended_actions: SignalActionItem[];
  trend_direction: SignalTrend | null;
  projected_impact: string | null;
  estimated_horizon_days: number | null;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  dismissed_by: string | null;
  dismissed_at: string | null;
  dismissal_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProactiveIntelligenceSummary {
  total_active_signals: number;
  critical_signals: number;
  high_signals: number;
  medium_signals: number;
  low_signals: number;
  signals_by_priority: Record<SignalPriority, number>;
  signals_by_type: Record<string, number>;
  top_signals: ProactiveSignal[];
  fleet_insights: string[];
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

  // M7 Proactive Intelligence Endpoints
  getProactiveSummary: (accessToken: string) =>
    apiRequest<ProactiveIntelligenceSummary>("/intelligence/summary", { accessToken }),

  getSignals: (
    accessToken: string,
    params?: {
      status?: SignalStatus;
      severity?: SignalSeverity;
      priority?: SignalPriority;
      signal_type?: SignalType;
      asset_id?: string;
    }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.severity) searchParams.set("severity", params.severity);
    if (params?.priority) searchParams.set("priority", params.priority);
    if (params?.signal_type) searchParams.set("signal_type", params.signal_type);
    if (params?.asset_id) searchParams.set("asset_id", params.asset_id);
    const qs = searchParams.toString();
    return apiRequest<ProactiveSignal[]>(`/intelligence/signals${qs ? `?${qs}` : ""}`, { accessToken });
  },

  getSignal: (accessToken: string, signalId: string) =>
    apiRequest<ProactiveSignal>(`/intelligence/signals/${signalId}`, { accessToken }),

  acknowledgeSignal: (accessToken: string, signalId: string) =>
    apiRequest<ProactiveSignal>(`/intelligence/signals/${signalId}/acknowledge`, {
      accessToken,
      method: "POST",
    }),

  inReviewSignal: (accessToken: string, signalId: string) =>
    apiRequest<ProactiveSignal>(`/intelligence/signals/${signalId}/in-review`, {
      accessToken,
      method: "POST",
    }),

  resolveSignal: (accessToken: string, signalId: string) =>
    apiRequest<ProactiveSignal>(`/intelligence/signals/${signalId}/resolve`, {
      accessToken,
      method: "POST",
    }),

  dismissSignal: (accessToken: string, signalId: string, reason?: string) =>
    apiRequest<ProactiveSignal>(`/intelligence/signals/${signalId}/dismiss`, {
      accessToken,
      method: "POST",
      body: reason ? { reason } : undefined,
    }),

  getAssetSignals: (accessToken: string, assetId: string) =>
    apiRequest<ProactiveSignal[]>(`/intelligence/assets/${assetId}/signals`, { accessToken }),

  // H8.3 Cross-Asset Fleet Correlation
  getFleetCorrelation: (
    accessToken: string,
    params?: { asset_id?: string; feature_family?: string; confidence?: string; days?: number }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.asset_id) searchParams.set("asset_id", params.asset_id);
    if (params?.feature_family) searchParams.set("feature_family", params.feature_family);
    if (params?.confidence) searchParams.set("confidence", params.confidence);
    if (params?.days) searchParams.set("days", params.days.toString());
    const qs = searchParams.toString();
    return apiRequest<FleetCorrelationContext>(`/intelligence/fleet/correlation${qs ? `?${qs}` : ""}`, { accessToken });
  },

  getFleetCorrelationDetail: (accessToken: string, correlationId: string) =>
    apiRequest<FleetAnomalyPatternCorrelation>(`/intelligence/fleet/correlation/${correlationId}`, { accessToken }),
};

export interface FleetAnomalyPatternCorrelation {
  id: string;
  organization_id: string;
  pattern_type: string;
  feature_family: string;
  participating_asset_ids: string[];
  participating_asset_count: number;
  participating_component_ids: string[];
  observation_count: number;
  similarity_score: number;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_EVIDENCE";
  lifecycle_status: "CANDIDATE" | "EVALUATED" | "SUPPORTED" | "INSUFFICIENT_EVIDENCE";
  sensor_compatibility: "COMPATIBLE" | "INCOMPATIBLE_UNITS" | "INCOMPATIBLE_SENSOR_TYPES" | "UNKNOWN";
  operating_conditions_comparable: boolean;
  is_simulation: boolean;
  evidence_references: Array<Record<string, any>>;
  supporting_signal_ids: string[];
  time_window_start?: string | null;
  time_window_end?: string | null;
  uncertainty_notes: string[];
  disclaimer: string;
  evaluated_at: string;
}

export interface FleetCorrelationContext {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  total_fleet_assets: number;
  affected_asset_count: number;
  affected_asset_percentage: number | null;
  total_active_signal_count: number;
  asset_correlations: Array<{
    asset_id: string;
    asset_registration: string | null;
    active_signal_count: number;
    highest_signal_severity: string | null;
    diagnostic_candidate_count: number;
    prognostic_record_count: number;
    has_rul_estimate: boolean;
    component_context_available: boolean;
    component_count: number | null;
    evidence_completeness: "COMPLETE" | "PARTIAL" | "INSUFFICIENT_DATA";
    evidence_note: string;
  }>;
  component_correlations: Array<{
    component_type: string;
    model: string | null;
    correlated_component_count: number;
    asset_ids: string[];
    signal_count: number;
    diagnostic_count: number;
    prognostic_count: number;
    basis: string;
  }>;
  anomaly_correlations: FleetAnomalyPatternCorrelation[];
  explanation: string[];
  evaluated_at: string;
}

