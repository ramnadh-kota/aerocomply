// Typed REAL-mode client for the backend HUMS foundation endpoints
// (backend/app/api/v1/hums.py). organization_id is never sent -- the
// backend derives it from the authenticated JWT (same convention as every
// other lib/api/*.ts client).
//
// Sensors, readings, asset health, exceedances, feature history, per-sensor limits. Diagnostics, prognostics/RUL and
// health intelligence have their own panels (components/intelligence/HUMS*Panel.tsx).

import { apiRequest } from "@/lib/apiClient";

export type HUMSHealthStatus = "HEALTHY" | "DEGRADED" | "CRITICAL" | "INSUFFICIENT_DATA";
export type HUMSConfidence = "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";

export interface HUMSSensor {
  id: string;
  asset_id: string;
  component_id: string | null;
  sensor_code: string;
  sensor_type: string;
  measurement_type: string;
  unit: string;
  installation_location: string | null;
  status: string;
  source: string;
  warning_threshold?: number | null;
  critical_threshold?: number | null;
  created_at: string;
}

export interface HUMSFeatureValue {
  parameter: string;
  value: number;
  unit: string;
  window_start: string;
  window_end: string;
  sample_count: number;
}

export interface HUMSComponentHealth {
  sensor_id: string;
  parameter: string;
  health_score: number | null;
  status: HUMSHealthStatus;
  latest_feature: HUMSFeatureValue | null;
  active_exceedance_count: number;
  confidence: HUMSConfidence;
}

export interface HUMSAssetHealthSummary {
  asset_id: string;
  overall_status: HUMSHealthStatus;
  sensor_count: number;
  active_exceedance_count: number;
  components: HUMSComponentHealth[];
  generated_at: string;
}

// H2 -- persisted, traceable feature-engine output (backend HUMSFeature).
export type HUMSFeatureQuality = "GOOD" | "DEGRADED" | "INSUFFICIENT_DATA" | "INVALID";

export interface HUMSFeature {
  id: string;
  sensor_id: string;
  asset_id: string;
  component_id: string | null;
  measurement_type: string;
  feature_type: string;
  value: number;
  unit: string;
  window_start: string;
  window_end: string;
  sample_count: number;
  quality: HUMSFeatureQuality;
  calculation_method: string;
  processor_version: string;
  created_at: string;
}

export interface HUMSSpectrum {
  sensor_id: string;
  unit: string;
  sampling_rate_hz: number | null;
  frequency_resolution_hz: number | null;
  frequencies_hz: number[];
  magnitudes: number[];
  dominant_frequency_hz: number | null;
  sample_count: number;
  window_start: string | null;
  window_end: string | null;
  quality: HUMSFeatureQuality;
}

// H3 -- baseline, deviation, trend, and explainable health intelligence.
export type HUMSBaselineQuality = "VALID" | "LIMITED" | "INSUFFICIENT_DATA" | "STALE" | "INVALID";
export type HUMSDeviationState = "NORMAL" | "ELEVATED" | "DEVIATED" | "SEVERE" | "INSUFFICIENT_DATA";
export type HUMSTrendDirection = "INCREASING" | "DECREASING" | "STABLE" | "VOLATILE" | "ACCELERATING" | "INSUFFICIENT_DATA";
export type HUMSHealthState = "HEALTHY" | "WATCH" | "DEGRADED" | "WARNING" | "CRITICAL" | "UNKNOWN" | "INSUFFICIENT_DATA";

export interface HUMSBaseline {
  id: string;
  asset_id: string;
  component_id: string | null;
  sensor_id: string;
  feature_type: string;
  baseline_scope: "ASSET" | "COMPONENT" | "FLEET";
  sample_count: number;
  mean: number;
  median: number;
  std_dev: number;
  minimum: number;
  maximum: number;
  percentile_05: number;
  percentile_25: number;
  percentile_50: number;
  percentile_75: number;
  percentile_95: number;
  lower_bound: number;
  upper_bound: number;
  calculation_method: string;
  source_window_start: string;
  source_window_end: string;
  version: number;
  is_current: boolean;
  quality: HUMSBaselineQuality;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
  context_notes: string | null;
  created_at: string;
}

export interface HUMSDeviation {
  sensor_id: string;
  feature_type: string;
  current_value: number;
  baseline_value: number;
  lower_bound: number;
  upper_bound: number;
  absolute_deviation: number;
  percentage_deviation: number | null;
  standardized_deviation: number | null;
  state: HUMSDeviationState;
  baseline_quality: string;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
}

export interface HUMSTrend {
  sensor_id: string;
  feature_type: string;
  direction: HUMSTrendDirection;
  slope: number | null;
  rate_of_change: number | null;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
  sample_count: number;
  rolling_mean: number | null;
  rolling_std: number | null;
}

export interface HUMSFeatureHealth {
  sensor_id: string;
  feature_type: string;
  state: HUMSHealthState;
  consecutive_deviation_count: number;
  explanation: string[];
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
  deviation: HUMSDeviation | null;
  trend: HUMSTrend | null;
}

export interface HUMSComponentHealthIntelligence {
  component_id: string | null;
  state: HUMSHealthState;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
  primary_contributors: HUMSFeatureHealth[];
  all_contributors: HUMSFeatureHealth[];
}

export interface HUMSAssetHealthIntelligence {
  asset_id: string;
  state: HUMSHealthState;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
  components: HUMSComponentHealthIntelligence[];
  primary_contributors: HUMSFeatureHealth[];
  generated_at: string;
}

// H4 -- rule-based diagnostic candidates and fault isolation. Never a
// confirmed fault unless status === "CONFIRMED" (only set by an explicit,
// authorized confirm action).
export type HUMSDiagnosticStatus = "CANDIDATE" | "SUPPORTED" | "WEAK" | "UNSUPPORTED" | "CONFIRMED" | "REJECTED" | "RESOLVED";
export type HUMSDiagnosticSeverity = "LOW" | "MEDIUM" | "HIGH";

export interface HUMSDiagnosticCandidate {
  id: string;
  asset_id: string;
  component_id: string | null;
  sensor_ids: string[];
  fault_code: string;
  fault_name: string;
  fault_domain: "VIBRATION" | "SENSOR";
  diagnostic_method: string;
  rule_version: string;
  status: HUMSDiagnosticStatus;
  severity: HUMSDiagnosticSeverity;
  score: number;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA";
  primary_evidence: Record<string, unknown>[];
  supporting_evidence: Record<string, unknown>[];
  contradicting_evidence: Record<string, unknown>[];
  explanation: string[];
  detected_at: string;
  confirmed_at: string | null;
  confirmed_by_user_id: string | null;
  rejected_at: string | null;
  rejected_by_user_id: string | null;
  rejection_reason: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

// H5 -- degradation trajectory models and RUL prognostics. Every RUL value
// is an ESTIMATE, NOT A CERTIFIED LIFE LIMIT.
export type HUMSModelType = "LINEAR" | "ROBUST_LINEAR" | "INSUFFICIENT_DATA";
export type HUMSTrajectoryState = "STABLE" | "DEGRADING" | "ACCELERATING" | "NON_MONOTONIC" | "INSUFFICIENT_DATA" | "UNKNOWN";
export type HUMSUsageUnit = "FLIGHT_HOURS" | "HOURS_ELAPSED";
export type HUMSThresholdType = "ENGINEERING_LIMIT" | "MAINTENANCE_THRESHOLD" | "WARNING_THRESHOLD" | "CONFIGURED_PROGNOSTIC_THRESHOLD";
export type HUMSPrognosticStatus = "AVAILABLE" | "LIMITED" | "INSUFFICIENT_DATA" | "LOW_CONFIDENCE" | "STALE" | "INVALID";

export interface HUMSDegradationModel {
  id: string;
  asset_id: string;
  component_id: string | null;
  sensor_id: string;
  feature_type: string;
  reference_baseline_id: string | null;
  model_type: HUMSModelType;
  model_version: string;
  fit_slope: number;
  fit_intercept: number;
  fit_error: number;
  r_squared: number;
  sample_count: number;
  usage_unit: HUMSUsageUnit;
  usage_span: number;
  trajectory_state: HUMSTrajectoryState;
  quality: string;
  confidence: string;
  version: number;
  is_current: boolean;
  created_at: string;
}

export interface HUMSPrognosticRecord {
  id: string;
  asset_id: string;
  component_id: string | null;
  sensor_id: string;
  feature_type: string;
  degradation_model_id: string | null;
  diagnostic_candidate_id: string | null;
  current_value: number;
  threshold_value: number | null;
  threshold_type: HUMSThresholdType | null;
  rul_estimate: number | null;
  rul_lower: number | null;
  rul_upper: number | null;
  rul_unit: HUMSUsageUnit | null;
  extrapolation_distance: number | null;
  confidence: "HIGH" | "MEDIUM" | "LOW" | "INSUFFICIENT_DATA" | "STALE";
  quality: string;
  status: HUMSPrognosticStatus;
  explanation: string[];
  observed_at: string;
  calculated_at: string;
  version: number;
  is_current: boolean;
}

export interface HUMSExceedance {
  id: string;
  sensor_id: string;
  asset_id: string;
  component_id: string | null;
  parameter: string;
  observed_value: number;
  threshold_value: number;
  severity: string;
  window_start: string;
  window_end: string;
  finding_id: string | null;
  created_at: string;
}

export const humsApi = {
  getAssetHealth: (accessToken: string, assetId: string) =>
    apiRequest<HUMSAssetHealthSummary>(`/hums/assets/${assetId}/health`, { accessToken }),

  getAssetExceedances: (accessToken: string, assetId: string) =>
    apiRequest<HUMSExceedance[]>(`/hums/assets/${assetId}/exceedances`, { accessToken }),

  setSensorThresholds: (
    accessToken: string,
    sensorId: string,
    payload: { warning_threshold: number | null; critical_threshold: number | null }
  ) => apiRequest<HUMSSensor>(`/hums/sensors/${sensorId}/thresholds`, { method: "PUT", body: payload, accessToken }),

  getSensors: (accessToken: string, assetId: string) =>
    apiRequest<HUMSSensor[]>(`/hums/sensors?asset_id=${assetId}`, { accessToken }),

  getAssetFeatures: (accessToken: string, assetId: string, featureType?: string) =>
    apiRequest<HUMSFeature[]>(
      `/hums/assets/${assetId}/features${featureType ? `?feature_type=${featureType}` : ""}`,
      { accessToken }
    ),

  getSensorFeatures: (accessToken: string, sensorId: string, featureType?: string) =>
    apiRequest<HUMSFeature[]>(
      `/hums/sensors/${sensorId}/features${featureType ? `?feature_type=${featureType}` : ""}`,
      { accessToken }
    ),

  getSensorSpectrum: (accessToken: string, sensorId: string) =>
    apiRequest<HUMSSpectrum>(`/hums/sensors/${sensorId}/spectrum`, { accessToken }),

  getAssetBaseline: (accessToken: string, assetId: string) =>
    apiRequest<HUMSBaseline[]>(`/hums/assets/${assetId}/baseline`, { accessToken }),

  getAssetTrends: (accessToken: string, assetId: string) =>
    apiRequest<HUMSTrend[]>(`/hums/assets/${assetId}/trends`, { accessToken }),

  getAssetDeviations: (accessToken: string, assetId: string) =>
    apiRequest<HUMSDeviation[]>(`/hums/assets/${assetId}/deviations`, { accessToken }),

  getAssetHealthIntelligence: (accessToken: string, assetId: string) =>
    apiRequest<HUMSAssetHealthIntelligence>(`/hums/assets/${assetId}/health-intelligence`, { accessToken }),

  getComponentHealth: (accessToken: string, componentId: string) =>
    apiRequest<HUMSComponentHealthIntelligence>(`/hums/components/${componentId}/health`, { accessToken }),

  getAssetDiagnostics: (accessToken: string, assetId: string) =>
    apiRequest<HUMSDiagnosticCandidate[]>(`/hums/assets/${assetId}/diagnostics`, { accessToken }),

  getComponentDiagnostics: (accessToken: string, componentId: string) =>
    apiRequest<HUMSDiagnosticCandidate[]>(`/hums/components/${componentId}/diagnostics`, { accessToken }),

  confirmDiagnostic: (accessToken: string, diagnosticId: string) =>
    apiRequest<HUMSDiagnosticCandidate>(`/hums/diagnostics/${diagnosticId}/confirm`, { accessToken, method: "POST" }),

  rejectDiagnostic: (accessToken: string, diagnosticId: string, reason: string) =>
    apiRequest<HUMSDiagnosticCandidate>(`/hums/diagnostics/${diagnosticId}/reject`, {
      accessToken,
      method: "POST",
      body: { reason },
    }),

  getAssetPrognostics: (accessToken: string, assetId: string) =>
    apiRequest<HUMSPrognosticRecord[]>(`/hums/assets/${assetId}/prognostics`, { accessToken }),

  getComponentPrognostics: (accessToken: string, componentId: string) =>
    apiRequest<HUMSPrognosticRecord[]>(`/hums/components/${componentId}/prognostics`, { accessToken }),

  getAssetDegradation: (accessToken: string, assetId: string) =>
    apiRequest<HUMSDegradationModel[]>(`/hums/assets/${assetId}/degradation`, { accessToken }),
};
