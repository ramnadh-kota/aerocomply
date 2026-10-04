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

  // H8.6 Consolidated Public Fleet Intelligence API
  getFleetOverview: (accessToken: string, params?: { days?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.days) searchParams.set("days", params.days.toString());
    const qs = searchParams.toString();
    return apiRequest<FleetIntelligenceContext>(`/intelligence/fleet/overview${qs ? `?${qs}` : ""}`, { accessToken });
  },

  getFleetSignals: (
    accessToken: string,
    params?: { severity?: string; signal_type?: string; asset_id?: string }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.severity) searchParams.set("severity", params.severity);
    if (params?.signal_type) searchParams.set("signal_type", params.signal_type);
    if (params?.asset_id) searchParams.set("asset_id", params.asset_id);
    const qs = searchParams.toString();
    return apiRequest<FleetSignalContext>(`/intelligence/fleet/signals${qs ? `?${qs}` : ""}`, { accessToken });
  },

  getFleetMRO: (
    accessToken: string,
    params?: { days?: number; candidate_status?: string }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.days) searchParams.set("days", params.days.toString());
    if (params?.candidate_status) searchParams.set("candidate_status", params.candidate_status);
    const qs = searchParams.toString();
    return apiRequest<FleetMROContext>(`/intelligence/fleet/mro${qs ? `?${qs}` : ""}`, { accessToken });
  },

  listMROCandidates: (
    accessToken: string,
    params?: { status?: string; candidate_type?: string; priority?: string }
  ) => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.candidate_type) searchParams.set("candidate_type", params.candidate_type);
    if (params?.priority) searchParams.set("priority", params.priority);
    const qs = searchParams.toString();
    return apiRequest<MaintenanceCandidate[]>(`/mro-intelligence/candidates${qs ? `?${qs}` : ""}`, { accessToken });
  },

  reviewCandidate: (accessToken: string, candidateId: string, notes?: string) =>
    apiRequest<MaintenanceCandidate>(`/mro-intelligence/candidates/${candidateId}/review`, {
      method: "POST",
      accessToken,
      body: JSON.stringify({ notes }),
    }),

  acceptCandidate: (accessToken: string, candidateId: string, notes?: string) =>
    apiRequest<MaintenanceCandidate>(`/mro-intelligence/candidates/${candidateId}/accept`, {
      method: "POST",
      accessToken,
      body: JSON.stringify({ notes }),
    }),

  rejectCandidate: (accessToken: string, candidateId: string, notes?: string) =>
    apiRequest<MaintenanceCandidate>(`/mro-intelligence/candidates/${candidateId}/reject`, {
      method: "POST",
      accessToken,
      body: JSON.stringify({ notes }),
    }),

  deferCandidate: (accessToken: string, candidateId: string, notes?: string) =>
    apiRequest<MaintenanceCandidate>(`/mro-intelligence/candidates/${candidateId}/defer`, {
      method: "POST",
      accessToken,
      body: JSON.stringify({ notes }),
    }),

  draftWorkOrderFromCandidate: (
    accessToken: string,
    candidateId: string,
    payload?: { title?: string; priority?: string; due_at?: string; notes?: string }
  ) =>
    apiRequest<CandidateDraftWorkOrderResponse>(`/mro-intelligence/candidates/${candidateId}/draft-work-order`, {
      method: "POST",
      accessToken,
      body: JSON.stringify(payload ?? {}),
    }),
};

export interface MaintenanceCandidate {
  id: string;
  asset_id: string;
  component_id?: string | null;
  candidate_type: string;
  status: string;
  priority: string;
  confidence: number;
  reason: string;
  dedup_key: string;
  source_lineage: Array<Record<string, any>>;
  operational_impact?: string | null;
  data_freshness?: string | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  review_notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CandidateDraftWorkOrderResponse {
  candidate: MaintenanceCandidate;
  work_order_id: string;
  work_order_number: string;
  work_order_status: string;
  work_order_priority: string;
  work_order_title: string;
}


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

export interface SourceLineageEntry {
  source_domain: string;
  source_service: string;
  source_entity: string;
  source_timestamp?: string | null;
  freshness: "FRESH" | "STALE" | "MISSING" | "UNKNOWN";
}

export interface FleetOverviewContext {
  organization_id: string;
  asset_count: number;
  active_asset_count: number;
  component_count: number;
  evaluated_at: string;
}

export interface FleetHealthContext {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  healthy_count: number;
  degraded_count: number;
  attention_count: number;
  unknown_count: number;
  explanation: string[];
}

export interface FleetTelemetryContext {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  fresh_count: number;
  stale_count: number;
  missing_count: number;
  unknown_count: number;
  hums_coverage_percentage?: number | null;
  explanation: string[];
}

export interface FleetAnalyticalContext {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  metrics: Record<string, any>;
  explanation: string[];
}

export interface FleetIntelligenceContext {
  organization_id: string;
  overview: FleetOverviewContext;
  health_context: FleetHealthContext;
  telemetry_context: FleetTelemetryContext;
  analytical_context: FleetAnalyticalContext;
  source_lineage: SourceLineageEntry[];
  evaluated_at: string;
}

export interface FleetSignalByAssetEntry {
  asset_id: string;
  asset_registration?: string | null;
  active_signal_count: number;
  highest_severity?: string | null;
}

export interface FleetRecentSignalEntry {
  id: string;
  signal_type: string;
  severity: string;
  status: string;
  title: string;
  asset_id?: string | null;
  detected_at: string;
}

export interface FleetSignalContext {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  total_active_signals: number;
  severity_distribution: Record<string, number>;
  signal_type_distribution: Record<string, number>;
  affected_asset_count: number;
  affected_component_count: number;
  signals_by_asset: FleetSignalByAssetEntry[];
  recent_signals: FleetRecentSignalEntry[];
  fleet_patterns: FleetRecentSignalEntry[];
  assets_with_signals_ratio?: string | null;
  explanation: string[];
}

export interface MROCandidateAggregationEntry {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  candidate_count: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  affected_asset_count: number;
  affected_component_count: number;
}

export interface MROComponentCorrelationEntry {
  component_id: string;
  component_type?: string | null;
  candidate_count: number;
  affected_asset_count: number;
  candidate_types: string[];
}

export interface MROComplianceImpactAggregationEntry {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  by_impact: Record<string, number>;
  evidence_missing_asset_count: number;
  bounded_asset_count: number;
  total_candidate_asset_count: number;
  explanation: string[];
}

export interface MROReadinessImpactAggregationEntry {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  by_readiness_impact: Record<string, number>;
  by_authoritative_readiness_state: Record<string, number>;
  bounded_asset_count: number;
  explanation: string[];
}

export interface MROOperationalImpactAggregationEntry {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  by_impact_level: Record<string, number>;
  candidate_count: number;
}

export interface MROConflictAggregationEntry {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  conflict_count: number;
  by_check_type: Record<string, number>;
  affected_asset_count: number;
  bounded_asset_count: number;
  explanation: string[];
}

export interface FleetMROAttentionComparison {
  mro_candidate_severity_distribution: Record<string, number>;
  proactive_signal_severity_distribution: Record<string, number>;
  note: string;
}

export interface HUMSOnlyAssetEntry {
  asset_id: string;
  asset_registration?: string | null;
  active_signal_count: number;
  diagnostic_candidate_count: number;
  prognostic_record_count: number;
  has_rul_estimate: boolean;
  note: string;
}

export interface FleetMROContext {
  availability: "AVAILABLE" | "DATA_UNAVAILABLE";
  total_fleet_assets: number;
  candidates: MROCandidateAggregationEntry;
  component_correlations: MROComponentCorrelationEntry[];
  compliance_impact: MROComplianceImpactAggregationEntry;
  readiness_impact: MROReadinessImpactAggregationEntry;
  operational_impact: MROOperationalImpactAggregationEntry;
  conflicts: MROConflictAggregationEntry;
  attention_comparison: FleetMROAttentionComparison;
  hums_only_assets: HUMSOnlyAssetEntry[];
  source_lineage: SourceLineageEntry[];
  explanation: string[];
  evaluated_at: string;
}

