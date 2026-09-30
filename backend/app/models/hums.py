"""HUMS (Health & Usage Monitoring System) domain models — H1 + H2 + H3.

H1 proved the pathway:
    Sensor -> SensorReading -> Feature (RMS) -> Exceedance -> Finding -> Evidence -> Signal

H2 adds HUMSFeature: a persisted, traceable record for every feature the
signal-processing engine computes (time-domain, frequency-domain, and
domain-specific), not just the single ad-hoc RMS value H1 computed inline.
See app/services/hums/ for the engine and docs/HUMS_FEATURE_ENGINE.md for
the full feature catalog.

H3 adds HUMSBaseline: a versioned, per-(sensor, feature_type) statistical
baseline (mean/std/percentiles/bounds) computed from HUMSFeature history.
Deviation and trend results are NOT separately persisted — see
docs/HUMS_BASELINE_ENGINE.md's "why no HUMSFeatureDeviation/HUMSTrend
table" section for the reasoning (they're cheap to derive on demand from a
bounded HUMSFeature query plus the current baseline, so persisting them
would just be a second, harder-to-keep-consistent copy of the same data).

Diagnostics (fault isolation/classification), prognostics/RUL, and the
digital twin layers are still NOT part of this codebase — see
docs/HUMS_ARCHITECTURE.md for the target architecture and what remains
unimplemented.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class HUMSSensor(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A physical or simulated sensor installed on an asset/component.

    `sensor_type`/`measurement_type`/`unit` are free-text (not enums) so new
    sensor kinds can be added without a schema migration, per the spec's
    "support additional sensor types without schema redesign" requirement.
    """

    __tablename__ = "hums_sensors"
    __table_args__ = (
        UniqueConstraint("organization_id", "asset_id", "sensor_code", name="uq_hums_sensor_org_asset_code"),
        Index("ix_hums_sensor_org_asset", "organization_id", "asset_id"),
        CheckConstraint(
            "(warning_threshold IS NULL AND critical_threshold IS NULL) OR "
            "(warning_threshold IS NOT NULL AND critical_threshold IS NOT NULL "
            "AND warning_threshold > 0 AND critical_threshold > warning_threshold)",
            name="ck_hums_sensor_thresholds",
        ),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sensor_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    # Operator-configured vibration RMS limits (OEM / maintenance-manual values). NULL/NULL = platform defaults.
    warning_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    installation_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SIMULATED"
    )  # SIMULATED | IMPORTED | LIVE — never claims LIVE without a real ingestion path


class HUMSSensorReading(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A single provenance-tracked telemetry measurement.

    `data_quality` follows the spec's data-quality taxonomy (VALID/SUSPECT/
    MISSING/OUT_OF_RANGE/STALE/DUPLICATE/INVALID) — health/feature
    calculations must account for this rather than treating all readings as
    equally trustworthy.
    """

    __tablename__ = "hums_sensor_readings"
    __table_args__ = (
        Index("ix_hums_reading_org_sensor_ts", "organization_id", "sensor_id", "recorded_at"),
        Index("ix_hums_reading_org_asset_ts", "organization_id", "asset_id", "recorded_at"),
    )

    sensor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hums_sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flights.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(32), nullable=False, default="VALID")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="SIMULATED")
    ingestion_batch: Mapped[str | None] = mapped_column(String(128), nullable=True)


class HUMSExceedance(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A detected threshold exceedance derived from one or more sensor readings.

    Distinct from Finding/Evidence: an Exceedance is a raw detection fact
    (observation -> anomaly boundary in the spec's terminology). Whether it
    becomes a Finding is a separate, explicit step — see hums_service.
    """

    __tablename__ = "hums_exceedances"
    __table_args__ = (
        Index("ix_hums_exceedance_org_asset", "organization_id", "asset_id"),
    )

    sensor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hums_sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True
    )
    parameter: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "vibration_rms"
    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contributing_reading_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )


class HUMSFeature(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """H2: One computed feature value over a signal window, fully traceable
    back to the sensor readings that produced it.

    `feature_type` is free-text (e.g. "rms", "peak", "crest_factor",
    "kurtosis", "dominant_frequency", "mean", "trend") rather than an enum,
    matching HUMSSensor.sensor_type/measurement_type's "no schema redesign
    for a new kind" rationale — see app/services/hums/feature_extractors.py
    for the catalog of feature_type values actually produced today.
    """

    __tablename__ = "hums_features"
    __table_args__ = (
        Index("ix_hums_feature_org_sensor_type_ts", "organization_id", "sensor_id", "feature_type", "window_end"),
        Index("ix_hums_feature_org_asset_type_ts", "organization_id", "asset_id", "feature_type", "window_end"),
    )

    sensor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hums_sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True
    )
    measurement_type: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_count: Mapped[int] = mapped_column(nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False, default="GOOD")  # GOOD|DEGRADED|INSUFFICIENT_DATA|INVALID
    calculation_method: Mapped[str] = mapped_column(String(128), nullable=False)
    processor_version: Mapped[str] = mapped_column(String(32), nullable=False, default="h2.1")
    source_reading_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    feature_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class HUMSBaseline(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """H3: A versioned statistical baseline for one (sensor, feature_type)
    pair, computed from historical HUMSFeature rows.

    Baselines are append-only/versioned, never overwritten: recomputing
    creates a new row with `version` incremented and `is_current=True`,
    flipping the previous row's `is_current` to False — so "how was this
    conclusion reached" stays answerable for a health verdict computed
    against an older baseline. `baseline_scope` is ASSET or COMPONENT today;
    FLEET is a documented extension point only (see
    docs/HUMS_BASELINE_ENGINE.md) — the domain model does not yet have a
    clean "asset class" grouping to key a fleet baseline off of.
    """

    __tablename__ = "hums_baselines"
    __table_args__ = (
        Index("ix_hums_baseline_org_sensor_feature_current", "organization_id", "sensor_id", "feature_type", "is_current"),
        Index("ix_hums_baseline_org_asset_feature", "organization_id", "asset_id", "feature_type"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sensor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hums_sensors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    baseline_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="ASSET")  # ASSET|COMPONENT|FLEET

    sample_count: Mapped[int] = mapped_column(nullable=False)
    mean: Mapped[float] = mapped_column(Float, nullable=False)
    median: Mapped[float] = mapped_column(Float, nullable=False)
    std_dev: Mapped[float] = mapped_column(Float, nullable=False)
    minimum: Mapped[float] = mapped_column(Float, nullable=False)
    maximum: Mapped[float] = mapped_column(Float, nullable=False)
    percentile_05: Mapped[float] = mapped_column(Float, nullable=False)
    percentile_25: Mapped[float] = mapped_column(Float, nullable=False)
    percentile_50: Mapped[float] = mapped_column(Float, nullable=False)
    percentile_75: Mapped[float] = mapped_column(Float, nullable=False)
    percentile_95: Mapped[float] = mapped_column(Float, nullable=False)
    lower_bound: Mapped[float] = mapped_column(Float, nullable=False)
    upper_bound: Mapped[float] = mapped_column(Float, nullable=False)

    calculation_method: Mapped[str] = mapped_column(String(128), nullable=False)
    source_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    quality: Mapped[str] = mapped_column(String(32), nullable=False)  # VALID|LIMITED|INSUFFICIENT_DATA|STALE|INVALID
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)  # HIGH|MEDIUM|LOW|INSUFFICIENT_DATA
    context_notes: Mapped[str | None] = mapped_column(String(255), nullable=True)


class HUMSDiagnosticCandidate(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """H4: A diagnostic hypothesis generated by rule-based fault-signature
    matching over H3 feature-health results — NOT a confirmed fault.

    Fault signatures themselves are a versioned, in-code registry (see
    app/services/hums/fault_signatures.py), not a DB table — see
    docs/HUMS_DIAGNOSTICS.md for why (the H0 audit found `rules_engine/` is
    an empty stub with no existing DB-driven rule convention to extend;
    building a full signature-editing data model for H4 alone would be
    over-engineering relative to what the rest of this codebase does for
    comparable domains). `rule_version` on each row records exactly which
    version of which signature produced it, so the row stays reproducible
    even after the code-level signature is later revised.

    Unique per (organization, asset, component, fault_code): re-evaluation
    UPDATES the existing row (refreshing score/evidence/timestamps) rather
    than creating a duplicate — same "dedupe by identity, not by event"
    pattern ProactiveSignalRecord already uses.
    """

    __tablename__ = "hums_diagnostic_candidates"
    __table_args__ = (
        UniqueConstraint("organization_id", "asset_id", "component_id", "fault_code", name="uq_hums_diag_org_asset_component_fault"),
        Index("ix_hums_diag_org_asset_status", "organization_id", "asset_id", "status"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sensor_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    fault_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fault_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fault_domain: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g. VIBRATION, SENSOR
    diagnostic_method: Mapped[str] = mapped_column(String(64), nullable=False, default="rule_based_signature_matching")
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # CANDIDATE|SUPPORTED|WEAK|UNSUPPORTED|CONFIRMED|REJECTED|RESOLVED --
    # only SUPPORTED/WEAK/CANDIDATE are ever set by the diagnostic engine
    # itself; CONFIRMED/REJECTED/RESOLVED are ONLY ever set by an
    # authorized human action (see app/services/hums/diagnostic_service.py
    # confirm_candidate/reject_candidate — never set automatically).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CANDIDATE")
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # LOW|MEDIUM|HIGH
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)  # HIGH|MEDIUM|LOW|INSUFFICIENT_DATA

    primary_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    supporting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    contradicting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    explanation: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class HUMSDegradationModel(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """H5: A fitted degradation trajectory model for one (sensor,
    feature_type) — versioned like HUMSBaseline (never overwritten; a
    recompute creates a new version and flips the previous row's
    is_current). `reference_baseline_id` points at a FIXED, immutable
    HUMSBaseline row (an older, non-`is_current` version is never mutated
    by H3) used as the stable degradation reference — see
    docs/HUMS_RUL_ENGINE.md's reference-baseline strategy for why this
    avoids H3's "continuously refreshing baseline absorbs the anomaly"
    pitfall.
    """

    __tablename__ = "hums_degradation_models"
    __table_args__ = (
        Index("ix_hums_degmodel_org_sensor_feature_current", "organization_id", "sensor_id", "feature_type", "is_current"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hums_sensors.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    reference_baseline_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hums_baselines.id", ondelete="SET NULL"), nullable=True)

    model_type: Mapped[str] = mapped_column(String(32), nullable=False)  # LINEAR|ROBUST_LINEAR|INSUFFICIENT_DATA
    model_version: Mapped[str] = mapped_column(String(16), nullable=False, default="h5.1")

    fit_slope: Mapped[float] = mapped_column(Float, nullable=False)
    fit_intercept: Mapped[float] = mapped_column(Float, nullable=False)
    fit_error: Mapped[float] = mapped_column(Float, nullable=False)  # RMSE
    r_squared: Mapped[float] = mapped_column(Float, nullable=False)

    sample_count: Mapped[int] = mapped_column(nullable=False)
    usage_unit: Mapped[str] = mapped_column(String(32), nullable=False)  # FLIGHT_HOURS|HOURS_ELAPSED
    usage_span: Mapped[float] = mapped_column(Float, nullable=False)

    trajectory_state: Mapped[str] = mapped_column(String(32), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)


class HUMSPrognosticRecord(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """H5: A persisted RUL/prognostic result derived from a
    HUMSDegradationModel — versioned/refreshed the same way (is_current).

    Every RUL value here is an ESTIMATE, NOT A CERTIFIED LIFE LIMIT — see
    docs/HUMS_PROGNOSTICS.md's safety-boundary section.
    """

    __tablename__ = "hums_prognostic_records"
    __table_args__ = (
        Index("ix_hums_prognostic_org_sensor_feature_current", "organization_id", "sensor_id", "feature_type", "is_current"),
        Index("ix_hums_prognostic_org_asset", "organization_id", "asset_id"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True)
    component_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hums_sensors.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    degradation_model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hums_degradation_models.id", ondelete="SET NULL"), nullable=True)
    diagnostic_candidate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hums_diagnostic_candidates.id", ondelete="SET NULL"), nullable=True)

    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # ENGINEERING_LIMIT|MAINTENANCE_THRESHOLD|WARNING_THRESHOLD|CONFIGURED_PROGNOSTIC_THRESHOLD

    rul_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rul_lower: Mapped[float | None] = mapped_column(Float, nullable=True)
    rul_upper: Mapped[float | None] = mapped_column(Float, nullable=True)
    rul_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)

    extrapolation_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    quality: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # AVAILABLE|LIMITED|INSUFFICIENT_DATA|LOW_CONFIDENCE|STALE|INVALID
    explanation: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


__all__ = [
    "HUMSSensor",
    "HUMSSensorReading",
    "HUMSExceedance",
    "HUMSFeature",
    "HUMSBaseline",
    "HUMSDiagnosticCandidate",
    "HUMSDegradationModel",
    "HUMSPrognosticRecord",
]
