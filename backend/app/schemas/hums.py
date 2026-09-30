"""H1: HUMS foundation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import model_validator, BaseModel, ConfigDict, Field

DataQuality = Literal["VALID", "SUSPECT", "MISSING", "OUT_OF_RANGE", "STALE", "DUPLICATE", "INVALID"]


class HUMSSensorCreate(BaseModel):
    asset_id: uuid.UUID
    component_id: uuid.UUID | None = None
    sensor_code: str
    sensor_type: str
    measurement_type: str
    unit: str
    installation_location: str | None = None
    source: str = "SIMULATED"


class HUMSSensorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    sensor_code: str
    sensor_type: str
    measurement_type: str
    unit: str
    installation_location: str | None
    status: str
    source: str
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    created_at: datetime


class HUMSSensorThresholdUpdate(BaseModel):
    """Both limits, or both null to return to the platform defaults."""

    warning_threshold: float | None = Field(default=None, allow_inf_nan=False, gt=0)
    critical_threshold: float | None = Field(default=None, allow_inf_nan=False, gt=0)

    @model_validator(mode="after")
    def _both_or_neither_and_ordered(self) -> "HUMSSensorThresholdUpdate":
        if (self.warning_threshold is None) != (self.critical_threshold is None):
            raise ValueError("warning_threshold and critical_threshold must be set together (or both null)")
        if self.warning_threshold is not None and self.critical_threshold <= self.warning_threshold:  # type: ignore[operator]
            raise ValueError("critical_threshold must be greater than warning_threshold")
        return self


class HUMSReadingIn(BaseModel):
    recorded_at: datetime
    value: float = Field(..., allow_inf_nan=False)  # NaN/Infinity would corrupt features and baselines
    unit: str
    flight_id: uuid.UUID | None = None
    data_quality: DataQuality = "VALID"


class HUMSReadingBatchCreate(BaseModel):
    readings: list[HUMSReadingIn] = Field(..., min_length=1, max_length=5000)
    ingestion_batch: str | None = None


class HUMSSensorReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_id: uuid.UUID
    asset_id: uuid.UUID
    flight_id: uuid.UUID | None
    recorded_at: datetime
    value: float
    unit: str
    data_quality: DataQuality
    source: str


class HUMSExceedanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    parameter: str
    observed_value: float
    threshold_value: float
    severity: str
    window_start: datetime
    window_end: datetime
    finding_id: uuid.UUID | None
    created_at: datetime


class HUMSFeatureValue(BaseModel):
    """A single computed feature over a reading window (e.g. vibration RMS)."""

    parameter: str
    value: float
    unit: str
    window_start: datetime
    window_end: datetime
    sample_count: int


class HUMSComponentHealth(BaseModel):
    """Normalized health indicator for one sensor's monitored parameter.

    `rul` fields are intentionally absent from this H1 slice — prognostics/RUL
    is not yet implemented (see docs/HUMS_ARCHITECTURE.md). Do not infer a
    remaining-useful-life value from `health_score` here.
    """

    sensor_id: uuid.UUID
    parameter: str
    health_score: float | None = Field(None, description="0-100, null if insufficient data")
    status: Literal["HEALTHY", "DEGRADED", "CRITICAL", "INSUFFICIENT_DATA"]
    latest_feature: HUMSFeatureValue | None
    active_exceedance_count: int
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]


class HUMSFeatureResponse(BaseModel):
    """H2: One persisted, traceable feature row (backend HUMSFeature)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sensor_id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    measurement_type: str
    feature_type: str
    value: float
    unit: str
    window_start: datetime
    window_end: datetime
    sample_count: int
    quality: Literal["GOOD", "DEGRADED", "INSUFFICIENT_DATA", "INVALID"]
    calculation_method: str
    processor_version: str
    created_at: datetime


class HUMSAssetHealthSummary(BaseModel):
    """Asset-level HUMS health rollup — one input into (not the sole authority over) readiness."""

    asset_id: uuid.UUID
    overall_status: Literal["HEALTHY", "DEGRADED", "CRITICAL", "INSUFFICIENT_DATA"]
    sensor_count: int
    active_exceedance_count: int
    components: list[HUMSComponentHealth]
    generated_at: datetime


class HUMSBaselineResponse(BaseModel):
    """H3: A versioned statistical baseline for one (sensor, feature_type)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    sensor_id: uuid.UUID
    feature_type: str
    baseline_scope: Literal["ASSET", "COMPONENT", "FLEET"]
    sample_count: int
    mean: float
    median: float
    std_dev: float
    minimum: float
    maximum: float
    percentile_05: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float
    lower_bound: float
    upper_bound: float
    calculation_method: str
    source_window_start: datetime
    source_window_end: datetime
    version: int
    is_current: bool
    quality: Literal["VALID", "LIMITED", "INSUFFICIENT_DATA", "STALE", "INVALID"]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    context_notes: str | None
    created_at: datetime


class HUMSDeviationResponse(BaseModel):
    """H3: How far a sensor's latest feature value is from its baseline, and why."""

    sensor_id: uuid.UUID
    feature_type: str
    current_value: float
    baseline_value: float
    lower_bound: float
    upper_bound: float
    absolute_deviation: float
    percentage_deviation: float | None
    standardized_deviation: float | None
    state: Literal["NORMAL", "ELEVATED", "DEVIATED", "SEVERE", "INSUFFICIENT_DATA"]
    baseline_quality: str
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]


class HUMSTrendResponse(BaseModel):
    """H3: Deterministic trend classification for one sensor's feature history."""

    sensor_id: uuid.UUID
    feature_type: str
    direction: Literal["INCREASING", "DECREASING", "STABLE", "VOLATILE", "ACCELERATING", "INSUFFICIENT_DATA"]
    slope: float | None
    rate_of_change: float | None
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    sample_count: int
    rolling_mean: float | None
    rolling_std: float | None


class HUMSFeatureHealthResponse(BaseModel):
    """H3: One feature's explainable health verdict."""

    sensor_id: uuid.UUID
    feature_type: str
    state: Literal["HEALTHY", "WATCH", "DEGRADED", "WARNING", "CRITICAL", "UNKNOWN", "INSUFFICIENT_DATA"]
    consecutive_deviation_count: int
    explanation: list[str]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    deviation: HUMSDeviationResponse | None
    trend: HUMSTrendResponse | None


class HUMSComponentHealthIntelligence(BaseModel):
    """H3: Aggregated, explainable health for one component (or the
    asset-level bucket of sensors with no component_id)."""

    component_id: uuid.UUID | None
    state: Literal["HEALTHY", "WATCH", "DEGRADED", "WARNING", "CRITICAL", "UNKNOWN", "INSUFFICIENT_DATA"]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    primary_contributors: list[HUMSFeatureHealthResponse]
    all_contributors: list[HUMSFeatureHealthResponse]


class HUMSAssetHealthIntelligence(BaseModel):
    """H3: Asset-level health intelligence rollup — explainable, not a bare
    score. This is a SEPARATE endpoint/response from H1's
    `HUMSAssetHealthSummary` (`GET /hums/assets/{id}/health`), which stays
    frozen on its original simple RMS-threshold logic so H1/H2 tests and
    behavior are unaffected — see docs/HUMS_HEALTH_INTELLIGENCE.md for why
    these are two endpoints rather than one.
    """

    asset_id: uuid.UUID
    state: Literal["HEALTHY", "WATCH", "DEGRADED", "WARNING", "CRITICAL", "UNKNOWN", "INSUFFICIENT_DATA"]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    components: list[HUMSComponentHealthIntelligence]
    primary_contributors: list[HUMSFeatureHealthResponse]
    generated_at: datetime


class HUMSDiagnosticCandidateResponse(BaseModel):
    """H4: A rule-based diagnostic hypothesis — NEVER a confirmed fault
    unless `status == "CONFIRMED"`, which only an authorized human action
    (`POST .../confirm`) can set.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    sensor_ids: list[str]
    fault_code: str
    fault_name: str
    fault_domain: Literal["VIBRATION", "SENSOR"]
    diagnostic_method: str
    rule_version: str
    status: Literal["CANDIDATE", "SUPPORTED", "WEAK", "UNSUPPORTED", "CONFIRMED", "REJECTED", "RESOLVED"]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    score: float
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    primary_evidence: list[dict]
    supporting_evidence: list[dict]
    contradicting_evidence: list[dict]
    explanation: list[str]
    detected_at: datetime
    confirmed_at: datetime | None
    confirmed_by_user_id: uuid.UUID | None
    rejected_at: datetime | None
    rejected_by_user_id: uuid.UUID | None
    rejection_reason: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class HUMSDiagnosticRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


class HUMSDegradationModelResponse(BaseModel):
    """H5: A fitted degradation-trajectory model."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    sensor_id: uuid.UUID
    feature_type: str
    reference_baseline_id: uuid.UUID | None
    model_type: Literal["LINEAR", "ROBUST_LINEAR", "INSUFFICIENT_DATA"]
    model_version: str
    fit_slope: float
    fit_intercept: float
    fit_error: float
    r_squared: float
    sample_count: int
    usage_unit: Literal["FLIGHT_HOURS", "HOURS_ELAPSED"]
    usage_span: float
    trajectory_state: Literal["STABLE", "DEGRADING", "ACCELERATING", "NON_MONOTONIC", "INSUFFICIENT_DATA", "UNKNOWN"]
    quality: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA", "INVALID", "STALE"]
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
    version: int
    is_current: bool
    created_at: datetime


class HUMSPrognosticRecordResponse(BaseModel):
    """H5: A RUL/prognostic result. ESTIMATE — NOT A CERTIFIED LIFE LIMIT."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    sensor_id: uuid.UUID
    feature_type: str
    degradation_model_id: uuid.UUID | None
    diagnostic_candidate_id: uuid.UUID | None
    current_value: float
    threshold_value: float | None
    threshold_type: Literal["ENGINEERING_LIMIT", "MAINTENANCE_THRESHOLD", "WARNING_THRESHOLD", "CONFIGURED_PROGNOSTIC_THRESHOLD"] | None
    rul_estimate: float | None
    rul_lower: float | None
    rul_upper: float | None
    rul_unit: Literal["FLIGHT_HOURS", "HOURS_ELAPSED"] | None
    extrapolation_distance: float | None
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA", "STALE"]
    quality: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA", "INVALID", "STALE"]
    status: Literal["AVAILABLE", "LIMITED", "INSUFFICIENT_DATA", "LOW_CONFIDENCE", "STALE", "INVALID"]
    explanation: list[str]
    observed_at: datetime
    calculated_at: datetime
    version: int
    is_current: bool
    created_at: datetime
    updated_at: datetime


class HUMSSpectrumResponse(BaseModel):
    """H2: On-demand (not persisted) DFT magnitude spectrum for the frontend
    frequency view. Computed fresh from the sensor's latest window rather
    than stored, since a full spectrum array per window is not needed for
    feature history/trending — only the scalar features (dominant_frequency,
    spectral_energy, band_energy) are persisted as HUMSFeature rows.
    """

    sensor_id: uuid.UUID
    unit: str
    sampling_rate_hz: float | None
    frequency_resolution_hz: float | None
    frequencies_hz: list[float]
    magnitudes: list[float]
    dominant_frequency_hz: float | None
    sample_count: int
    window_start: datetime | None
    window_end: datetime | None
    quality: Literal["GOOD", "DEGRADED", "INSUFFICIENT_DATA", "INVALID"]


__all__ = [
    "HUMSSensorCreate",
    "HUMSSensorThresholdUpdate",
    "HUMSSensorResponse",
    "HUMSReadingIn",
    "HUMSReadingBatchCreate",
    "HUMSSensorReadingResponse",
    "HUMSExceedanceResponse",
    "HUMSFeatureValue",
    "HUMSFeatureResponse",
    "HUMSSpectrumResponse",
    "HUMSComponentHealth",
    "HUMSAssetHealthSummary",
    "HUMSBaselineResponse",
    "HUMSDeviationResponse",
    "HUMSTrendResponse",
    "HUMSFeatureHealthResponse",
    "HUMSComponentHealthIntelligence",
    "HUMSAssetHealthIntelligence",
    "HUMSDiagnosticCandidateResponse",
    "HUMSDiagnosticRejectRequest",
    "HUMSDegradationModelResponse",
    "HUMSPrognosticRecordResponse",
]
