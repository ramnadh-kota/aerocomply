"""H8.0: Fleet Intelligence Contract & Foundation.

This module defines the shared CONTEXT contract for fleet-level intelligence.
It is a foundation/contract layer only -- it does not itself compute
anything. H8.1 (app.services.intelligence.cross_asset_intelligence_service)
is the first consumer/populator of this shape.

CRITICAL data-authority boundary (do not violate in any future milestone):
  - H3 (app.services.hums_service / app.services.hums.health_service) is the
    ONLY authoritative source for asset/component HEALTH state.
  - H4 (app.services.hums.diagnostic_service) is the ONLY authoritative
    source for DIAGNOSTIC candidates.
  - H5 (app.services.hums.prognostic_service / degradation_service) is the
    ONLY authoritative source for RUL / prognostic estimates.
  - H7 (app.services.mro_intelligence_service) is the ONLY authoritative
    source for asset-scoped MRO/compliance/readiness correlation.
  - M7 (app.services.intelligence.proactive_intelligence_service) is the
    ONLY authoritative source for proactive signal lifecycle, fleet
    alerting, and attention ranking.

This contract (and everything M14/H8 derive into it) is a DERIVED,
READ-TIME, query-time DESCRIPTIVE ANALYTICS layer. It never re-implements,
overrides, or is treated as a substitute source of truth for any of the
above. Nothing in this contract is persisted -- there is no FleetState /
FleetHealth / FleetSignal table. Every response is recomputed from
authoritative records on each request.

As of H8.0/H8.1: M7 fleet signals/attention are NOT integrated here, H7
asset MRO/readiness/compliance intelligence is NOT integrated here, LISA
tools do NOT reference this contract, and no frontend surface exists yet.
Those are later H8 milestones (see docs/H8_FLEET_HUMS_INTELLIGENCE.md).

H8.2 EXTENSION: adds FleetSignalContext, a descriptive read-time
aggregation of M7's OWN persisted ProactiveSignalRecord rows (see
app.services.intelligence.cross_asset_intelligence_service
.evaluate_fleet_signal_aggregation). M7 (app.services.intelligence
.proactive_intelligence_service) remains the sole owner of signal
detection, severity/priority assignment, lifecycle transitions, fleet
attention ranking, and fleet pattern detection. H8.2 never recomputes any
of those -- it only buckets/counts M7's existing persisted output and
exposes M7's existing FLEET_PATTERN signals as-is.

H8.3 EXTENSION: adds FleetCorrelationContext, a descriptive read-time
CORRELATION of M7 signals, M14 fleet population, H4 diagnostic
candidates, H5 prognostic/RUL estimates, and H6 digital-twin component
context (see app.services.intelligence.cross_asset_intelligence_service
.evaluate_fleet_hums_correlation). H8.3 consumes existing intelligence
only -- it never recomputes health, diagnoses, RUL, degradation models,
signal severity, or fleet attention. All associations are deterministic
(same asset / same component / same component type-model / same signal
type) -- never a fabricated numeric correlation score. Language stays
ASSOCIATED/OBSERVED/CORRELATED -- never FAILED/DEFECTIVE/ROOT CAUSE/
(NOT) AIRWORTHY unless quoting an existing authoritative field verbatim.

H8.4 EXTENSION: adds FleetMROContext, a descriptive read-time AGGREGATION
of H7's OWN persisted MaintenanceIntelligenceCandidate rows (see
app.services.intelligence.cross_asset_intelligence_service
.evaluate_fleet_mro_aggregation), composed with H7's compliance/
readiness/operational-impact/conflict read functions (bounded per-asset,
mirroring H8.3's digital-twin cap) and H8.3's own correlation output.
H8.4 NEVER creates, modifies, approves, schedules, or executes
maintenance actions, and it never calls any H7 lifecycle mutation
(generate_maintenance_candidates/accept_candidate/reject_candidate/
review_candidate/defer_candidate). Its most important behavior is the
no-inference safety boundary: when an M7 signal / H4 diagnostic / H5
prognostic record exists for an asset but NO H7
MaintenanceIntelligenceCandidate exists for it, H8.4 reports that HUMS
evidence as context only (via `hums_only_assets`) -- it never creates or
implies an MRO candidate for that asset.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrors app.schemas.mro_intelligence.DataAvailability -- same convention:
# a sub-state whose source data is missing is explicit, never silently
# defaulted to a positive/healthy value.
DataAvailability = Literal["AVAILABLE", "DATA_UNAVAILABLE"]

Freshness = Literal["FRESH", "STALE", "MISSING", "UNKNOWN"]


class SourceLineageEntry(BaseModel):
    """One pointer back to the authoritative domain/service/record that
    contributed to a derived fleet-context value.

    Mirrors app.schemas.mro_intelligence.SourceLineageRef's "ID/label only,
    never copied field data" convention, extended with the domain/service
    that owns the record so a future consumer can tell at a glance which
    authoritative module (H3/H4/H5/H7/M7/M14) a given number traces back to.
    """

    source_domain: str  # e.g. "H3_HEALTH", "H4_DIAGNOSTICS", "H5_PROGNOSTICS", "M14_CROSS_ASSET"
    source_service: str  # e.g. "app.services.hums_service", "app.services.intelligence.cross_asset_intelligence_service"
    source_entity: str  # e.g. "HUMSExceedance", "ProactiveSignalRecord" -- table/record type, not a specific row
    source_timestamp: datetime | None = None  # when the underlying data was last observed/computed, if known
    freshness: Freshness = "UNKNOWN"


class FleetOverviewContext(BaseModel):
    """Population-level counts. No health/compliance judgment here."""

    organization_id: uuid.UUID
    asset_count: int
    active_asset_count: int
    component_count: int
    evaluated_at: datetime


class FleetHealthContext(BaseModel):
    """Descriptive aggregation of ALREADY-COMPUTED H3 asset health state.

    Never a new scoring algorithm -- see cross_asset_intelligence_service
    for exactly how these buckets are derived (from persisted
    ProactiveSignalRecord health-degradation signals + HUMS sensor
    presence, never a re-run of the H3 health engine).
    """

    availability: DataAvailability
    healthy_count: int
    degraded_count: int
    attention_count: int
    unknown_count: int
    explanation: list[str] = Field(default_factory=list)


class FleetTelemetryContext(BaseModel):
    """Descriptive aggregation of telemetry freshness, reusing H8's
    existing freshness-policy resolution (app.services.telemetry_service
    .resolve_effective_freshness_policy) -- never a new threshold."""

    availability: DataAvailability
    fresh_count: int
    stale_count: int
    missing_count: int
    unknown_count: int
    hums_coverage_percentage: float | None = None
    explanation: list[str] = Field(default_factory=list)


class FleetAnalyticalContext(BaseModel):
    """Free-form slot for the descriptive analytical metrics M14 (H8.1)
    produces: exceedance distribution, component distribution, diagnostic
    distribution, prognostic distribution. Kept loosely typed here
    (dict payloads) because H8.0's job is the envelope/contract, not
    pinning M14's evolving metric shapes -- M14's own dataclasses
    (see cross_asset_intelligence_service.py) are the source of truth for
    exact field names; this is a read-only passthrough summary.
    """

    availability: DataAvailability
    metrics: dict[str, object] = Field(default_factory=dict)
    explanation: list[str] = Field(default_factory=list)


class FleetSignalByAssetEntry(BaseModel):
    """One asset's active M7 signal count -- descriptive only."""

    asset_id: uuid.UUID
    asset_registration: str | None = None
    active_signal_count: int
    highest_severity: str | None = None  # CRITICAL/HIGH/MEDIUM/LOW, or None if somehow unresolved


class FleetRecentSignalEntry(BaseModel):
    """Small bounded passthrough of an M7 ProactiveSignalRecord -- ID/label
    fields only, mirroring SourceLineageEntry's "pointer, not a copy of
    business logic" convention. Full signal detail remains M7's
    ProactiveSignalResponse (app.schemas.intelligence_signal)."""

    id: uuid.UUID
    signal_type: str
    severity: str
    status: str
    title: str
    asset_id: uuid.UUID | None = None
    detected_at: datetime


class FleetSignalContext(BaseModel):
    """H8.2: Descriptive aggregation of M7's OWN persisted proactive
    signals (ProactiveSignalRecord). Every count here is a bucket/tally
    over M7's existing severity and signal_type vocabulary
    (app.schemas.intelligence_signal.SignalSeverity / SignalType) -- H8.2
    introduces no new severity, no new signal type, no new ranking, and no
    new pattern-detection logic. `fleet_patterns` is M7's own
    FLEET_PATTERN-typed signal rows, exposed as-is (not recomputed).
    """

    availability: DataAvailability
    total_active_signals: int
    severity_distribution: dict[str, int] = Field(default_factory=dict)
    signal_type_distribution: dict[str, int] = Field(default_factory=dict)
    affected_asset_count: int
    affected_component_count: int
    signals_by_asset: list[FleetSignalByAssetEntry] = Field(default_factory=list)
    recent_signals: list[FleetRecentSignalEntry] = Field(default_factory=list)
    fleet_patterns: list[FleetRecentSignalEntry] = Field(default_factory=list)
    # M7 signal count / M14 population count composition (H8.2's only
    # correlation): "X of Y fleet assets have active signals".
    assets_with_signals_ratio: str | None = None  # e.g. "2/5"
    explanation: list[str] = Field(default_factory=list)


class ComponentTypeCorrelationEntry(BaseModel):
    """H8.3: components of the SAME component_type (and, where set, the
    SAME model) that appear across more than one M7 signal / H4 diagnostic
    candidate / H5 prognostic record. Descriptive population-level
    observation only -- never a shared-fault-cause claim."""

    component_type: str
    model: str | None = None
    correlated_component_count: int
    asset_ids: list[uuid.UUID] = Field(default_factory=list)
    signal_count: int = 0
    diagnostic_count: int = 0
    prognostic_count: int = 0
    basis: str  # e.g. "SAME_COMPONENT_TYPE_AND_MODEL" / "SAME_COMPONENT_TYPE"


class SignalDiagnosticAssociation(BaseModel):
    """H8.3: an M7 signal and an H4 diagnostic candidate that share the
    same asset (and, where both set it, the same component). Exposed as
    an existing-record association, never as "H8 diagnosed"."""

    signal_id: uuid.UUID
    diagnostic_candidate_id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None = None
    relationship: Literal["SIGNAL_ASSOCIATED_WITH_DIAGNOSTIC_CANDIDATE"] = (
        "SIGNAL_ASSOCIATED_WITH_DIAGNOSTIC_CANDIDATE"
    )
    basis: str  # e.g. "SAME_ASSET_AND_COMPONENT" / "SAME_ASSET"


class SignalPrognosticAssociation(BaseModel):
    """H8.3: an M7 signal and an H5 prognostic/RUL record that share the
    same asset (and, where both set it, the same component). Exposed as
    an existing-record association, never as "H8 predicts"."""

    signal_id: uuid.UUID
    prognostic_record_id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None = None
    relationship: Literal["SIGNAL_ASSOCIATED_WITH_RUL_ESTIMATE"] = (
        "SIGNAL_ASSOCIATED_WITH_RUL_ESTIMATE"
    )
    basis: str


class AssetCorrelationEntry(BaseModel):
    """H8.3: per-affected-asset composition of M7 + H4 + H5 + H6 context.
    Only populated fields carry real data; absent fields are None, never
    fabricated. Bounded to the affected-asset set (never the whole
    fleet) to avoid N+1 digital-twin calls at fleet scale.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    asset_id: uuid.UUID
    asset_registration: str | None = None
    active_signal_count: int = 0
    highest_signal_severity: str | None = None
    diagnostic_candidate_count: int = 0
    prognostic_record_count: int = 0
    has_rul_estimate: bool = False
    assets_with_rul_estimate: bool = False
    component_context_available: bool = False
    component_count: int | None = None
    evidence_completeness: Literal["COMPLETE", "PARTIAL", "INSUFFICIENT_DATA"]
    evidence_note: str


class FleetAnomalyPatternCorrelation(BaseModel):
    """H8.3: A deterministic cross-asset anomaly pattern correlation.
    Identifies similar vibration/exceedance anomaly signatures across multiple assets
    under comparable operational observation windows.

    CRITICAL SAFETY & GOVERNANCE INVARIANT:
    Statistical similarity across fleet observations does NOT establish causality,
    common initiating mechanism, or shared physical origin. Airframe variations,
    duty cycles, and operating conditions must be reviewed by qualified engineering
    personnel before taking any corrective maintenance disposition.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    pattern_type: str  # e.g., "VIBRATION_EXCEEDANCE_PATTERN", "VIBRATION_FEATURE_ANOMALY"
    feature_family: str  # e.g., "vibration_rms", "vibration_peak", "kurtosis"
    participating_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    participating_asset_count: int
    participating_component_ids: list[uuid.UUID] = Field(default_factory=list)
    observation_count: int
    similarity_score: float  # [0.0, 1.0] deterministic statistical metric: 1.0 - CV
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_EVIDENCE"]
    lifecycle_status: Literal["CANDIDATE", "EVALUATED", "SUPPORTED", "INSUFFICIENT_EVIDENCE"]
    sensor_compatibility: Literal["COMPATIBLE", "INCOMPATIBLE_UNITS", "INCOMPATIBLE_SENSOR_TYPES", "UNKNOWN"]
    operating_conditions_comparable: bool
    is_simulation: bool
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    supporting_signal_ids: list[uuid.UUID] = Field(default_factory=list)
    time_window_start: datetime | None = None
    time_window_end: datetime | None = None
    uncertainty_notes: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Statistical correlation detected across fleet observations. "
        "Correlation does not imply shared physical origin, common initiating mechanism, or causality. "
        "Operational conditions and airframe variations must be reviewed by qualified engineering personnel."
    )
    evaluated_at: datetime


class FleetCorrelationContext(BaseModel):
    """H8.3's top-level output: a descriptive, deterministic CORRELATION
    of already-authoritative M7/M14/H4/H5/H6 output. Never a new fleet
    health/risk/attention score. See
    cross_asset_intelligence_service.evaluate_fleet_hums_correlation for
    exactly how each field is derived; docs/H8_FLEET_HUMS_INTELLIGENCE.md
    documents every deterministic correlation rule.
    """

    model_config = ConfigDict(from_attributes=True)

    availability: DataAvailability
    total_fleet_assets: int
    affected_asset_count: int
    affected_asset_percentage: float | None = None
    total_active_signal_count: int
    asset_correlations: list[AssetCorrelationEntry] = Field(default_factory=list)
    component_correlations: list[ComponentTypeCorrelationEntry] = Field(default_factory=list)
    signal_diagnostic_associations: list[SignalDiagnosticAssociation] = Field(default_factory=list)
    signal_prognostic_associations: list[SignalPrognosticAssociation] = Field(default_factory=list)
    anomaly_correlations: list[FleetAnomalyPatternCorrelation] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class MROCandidateAggregationEntry(BaseModel):
    """H8.4: bucket/tally over H7's OWN MaintenanceIntelligenceCandidate
    vocabulary (MROCandidateType/MROCandidateStatus/MROCandidatePriority).
    No new severity/type/status vocabulary is introduced here."""

    availability: DataAvailability
    candidate_count: int
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    affected_asset_count: int
    affected_component_count: int


class MROComponentCorrelationEntry(BaseModel):
    """One component associated with existing H7 MRO candidates.
    Never 'defective'/'failed' language -- see module docstring."""

    component_id: uuid.UUID
    component_type: str | None = None
    candidate_count: int
    affected_asset_count: int
    candidate_types: list[str] = Field(default_factory=list)


class MROComplianceImpactAggregationEntry(BaseModel):
    """Bounded (<=50 affected assets, mirrors H8.3's twin-lookup cap)
    aggregation of H7's own get_compliance_impact per-asset classification.
    EVIDENCE_MISSING (H7's UNKNOWN bucket, i.e. no compliance obligations
    found) is NEVER folded into NON_COMPLIANT."""

    availability: DataAvailability
    by_impact: dict[str, int] = Field(default_factory=dict)
    evidence_missing_asset_count: int = 0
    bounded_asset_count: int = 0
    total_candidate_asset_count: int = 0
    explanation: list[str] = Field(default_factory=list)


class MROReadinessImpactAggregationEntry(BaseModel):
    """Preserves H7's own authoritative-readiness-vs-readiness-impact
    distinction as two SEPARATE distributions -- never merged into one
    field or a new fleet readiness score."""

    availability: DataAvailability
    by_readiness_impact: dict[str, int] = Field(default_factory=dict)
    by_authoritative_readiness_state: dict[str, int] = Field(default_factory=dict)
    bounded_asset_count: int = 0
    explanation: list[str] = Field(default_factory=list)


class MROOperationalImpactAggregationEntry(BaseModel):
    """Counts H7's own persisted candidate.operational_impact values --
    no independent optimization/availability score."""

    availability: DataAvailability
    by_impact_level: dict[str, int] = Field(default_factory=dict)
    candidate_count: int = 0


class MROConflictAggregationEntry(BaseModel):
    """Bounded aggregation of H7's own detect_conflicts output. Conflicts
    are reported only -- H8.4 never auto-resolves them."""

    availability: DataAvailability
    conflict_count: int = 0
    by_check_type: dict[str, int] = Field(default_factory=dict)
    affected_asset_count: int = 0
    bounded_asset_count: int = 0
    explanation: list[str] = Field(default_factory=list)


class FleetMROAttentionComparison(BaseModel):
    """Two SEPARATE evidence streams -- H7 candidate severity distribution
    and M7 proactive signal severity distribution -- explicitly NOT merged
    into a combined 'Fleet Maintenance Priority/Risk/Urgency Score'."""

    mro_candidate_severity_distribution: dict[str, int] = Field(default_factory=dict)
    proactive_signal_severity_distribution: dict[str, int] = Field(default_factory=dict)
    note: str


class HUMSOnlyAssetEntry(BaseModel):
    """H8.4's critical safety-boundary output: an asset with M7/H4/H5
    evidence (per H8.3's own correlation) but NO H7
    MaintenanceIntelligenceCandidate. Reported as HUMS context only --
    never as an implied maintenance candidate/requirement."""

    asset_id: uuid.UUID
    asset_registration: str | None = None
    active_signal_count: int = 0
    diagnostic_candidate_count: int = 0
    prognostic_record_count: int = 0
    has_rul_estimate: bool = False
    note: str


class FleetMROContext(BaseModel):
    """H8.4's top-level output: a descriptive, read-time AGGREGATION of
    H7's own asset-level MRO/compliance/readiness/operational-impact/
    conflict correlation. Never a new MRO engine, compliance engine,
    readiness engine, work-order engine, or fleet MRO score. See
    cross_asset_intelligence_service.evaluate_fleet_mro_aggregation for
    exactly how each field is derived; docs/H8_FLEET_HUMS_INTELLIGENCE.md
    documents the full H8.4 reuse map and safety boundary.
    """

    availability: DataAvailability
    total_fleet_assets: int
    candidates: MROCandidateAggregationEntry
    component_correlations: list[MROComponentCorrelationEntry] = Field(default_factory=list)
    compliance_impact: MROComplianceImpactAggregationEntry
    readiness_impact: MROReadinessImpactAggregationEntry
    operational_impact: MROOperationalImpactAggregationEntry
    conflicts: MROConflictAggregationEntry
    attention_comparison: FleetMROAttentionComparison
    hums_only_assets: list[HUMSOnlyAssetEntry] = Field(default_factory=list)
    source_lineage: list[SourceLineageEntry] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
    evaluated_at: datetime


class FleetIntelligenceContext(BaseModel):
    """H8.0's top-level contract. Represents CONTEXT, not persistent state.

    Every field here is derived at read time from authoritative records.
    No field on this model is ever written back to an authoritative table.
    """

    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    overview: FleetOverviewContext
    health_context: FleetHealthContext
    telemetry_context: FleetTelemetryContext
    analytical_context: FleetAnalyticalContext
    source_lineage: list[SourceLineageEntry] = Field(default_factory=list)
    evaluated_at: datetime


# --- H8.5: LISA AI Fleet Intelligence Grounding Contract -------------------

class LisaFleetIntelligenceQuery(BaseModel):
    """Input query context for LISA Fleet Intelligence requests (H8.5)."""
    model_config = ConfigDict(from_attributes=True)

    organization_id: uuid.UUID
    question: str
    classified_intent: str
    asset_id: uuid.UUID | None = None
    feature_family: str | None = None
    pattern_type: str | None = None
    confidence: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_EVIDENCE"] | None = None
    time_window_days: int = 30
    is_simulation: bool | None = None


class LisaFleetIntelligenceClaimProvenance(BaseModel):
    """Deterministic source lineage for individual claims made by LISA (H8.5)."""
    model_config = ConfigDict(from_attributes=True)

    claim: str
    source_type: Literal[
        "H8_3_CORRELATION",
        "M7_PROACTIVE_SIGNAL",
        "HUMS_FEATURE",
        "EVIDENCE_RECORD",
        "AEROSPACE_INTELLIGENCE",
    ]
    source_id: str
    organization_id: uuid.UUID
    is_simulation: bool = False
    observation_window: str | None = None


class LisaFleetIntelligenceResponse(BaseModel):
    """Tenant-scoped, grounded response model for fleet intelligence (H8.5)."""
    model_config = ConfigDict(from_attributes=True)

    query: str
    intent: str
    headline: str
    observed_facts: list[str] = Field(default_factory=list)
    statistical_correlations: list[str] = Field(default_factory=list)
    engineering_interpretation: str | None = None
    uncertainty_and_limitations: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    participating_asset_ids: list[uuid.UUID] = Field(default_factory=list)
    participating_registrations: list[str] = Field(default_factory=list)
    correlation_references: list[uuid.UUID] = Field(default_factory=list)
    signal_references: list[uuid.UUID] = Field(default_factory=list)
    evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    is_simulation: bool = False
    data_freshness_status: str = "CURRENT"
    provenance: list[LisaFleetIntelligenceClaimProvenance] = Field(default_factory=list)
    disclaimer: str = (
        "Statistical correlation detected across fleet observations. "
        "Correlation does not imply shared physical origin, common initiating mechanism, or causality. "
        "Operational conditions and airframe variations must be reviewed by qualified engineering personnel."
    )

