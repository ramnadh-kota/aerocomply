"""H5: Usage normalization, reference-baseline selection, and persisted
HUMSDegradationModel fitting. The only module in this package (besides
prognostic_service.py) that touches the DB for H5.

Usage normalization reuses the EXISTING flight-hours/cycles architecture
(`flight_service.get_utilization`, `AssetHistoricalBaseline`) rather than
duplicating it — per H5 spec section 10's explicit instruction. When an
asset has no Flight records, usage falls back to wall-clock elapsed hours
(`HOURS_ELAPSED`), honestly labeled as a lower-fidelity proxy rather than
silently pretending flight-hour precision that doesn't exist.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.component import Component
from app.models.flight import Flight
from app.models.hums import HUMSBaseline, HUMSDegradationModel, HUMSFeature, HUMSSensor
from app.models.installation_history import ComponentInstallation
from app.services import flight_service
from app.services.hums.degradation_engine import (
    MIN_SAMPLES_FOR_DEGRADATION,
    determine_trajectory_state,
    select_model,
)

# Feature types where a HIGHER value means MORE degraded (vs. lower).
# Extension point: add a feature_type here as new degradation-relevant
# features are wired in (mirrors HEALTH_FEATURES_BY_MEASUREMENT_TYPE in
# health_service.py).
DEGRADING_UPWARD_FEATURES = {"rms", "kurtosis", "crest_factor", "peak", "peak_to_peak"}

DEGRADATION_MODEL_VERSION = "h5.1"
MAX_TRAJECTORY_POINTS = 60  # bounded feature-history window for fitting, same convention as H3's FEATURE_HISTORY_LIMIT


def degrading_direction(feature_type: str) -> int:
    return 1 if feature_type in DEGRADING_UPWARD_FEATURES else -1


def get_reference_baseline(db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, feature_type: str) -> HUMSBaseline | None:
    """Selects a STABLE reference baseline -- deliberately NOT the
    continuously-refreshing `is_current` HUMSBaseline H3 exposes (see
    docs/HUMS_RUL_ENGINE.md's "critical baseline lesson from H3": a
    continuously moving reference can absorb a sustained anomaly as new
    normal, which would silently erase the degradation H5 is trying to
    measure).

    Strategy: the EARLIEST baseline version (version=1) for this
    (sensor, feature_type) -- a fixed, immutable historical row, never
    itself recomputed once superseded. If the sensor's component has a
    more recent installation record (Strategy B: maintenance reset), the
    earliest baseline version created AFTER that installation is used
    instead, so a component replacement/overhaul starts a fresh reference
    rather than measuring degradation against a predecessor unit's history.
    """
    reset_after: datetime.datetime | None = None
    if sensor.component_id:
        latest_installation = db.execute(
            select(ComponentInstallation)
            .where(ComponentInstallation.organization_id == organization_id, ComponentInstallation.component_id == sensor.component_id)
            .order_by(ComponentInstallation.installed_at.desc())
        ).scalars().first()
        if latest_installation:
            reset_after = latest_installation.installed_at

    query = select(HUMSBaseline).where(
        HUMSBaseline.organization_id == organization_id,
        HUMSBaseline.sensor_id == sensor.id,
        HUMSBaseline.feature_type == feature_type,
    )
    if reset_after is not None:
        query = query.where(HUMSBaseline.source_window_start >= reset_after)
    query = query.order_by(HUMSBaseline.version.asc())

    return db.execute(query).scalars().first()


def _usage_hours_asof(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, asof: datetime.datetime) -> float:
    util = flight_service.get_utilization(db, organization_id=organization_id, asset_id=asset_id, until=asof)
    return round(float(util["total_minutes"]) / 60.0, 4)


def get_usage_anchor(db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, feature_type: str) -> datetime.datetime | None:
    """The fixed zero-point for HOURS_ELAPSED usage: the reference
    baseline's source window start if one exists, else the sensor's
    earliest recorded feature for this feature_type. MUST be identical
    across every call for the same (sensor, feature_type) — the model fit
    and any later drift check over a different row subset both call this,
    and using two different zero-points for the same trajectory would
    silently corrupt the usage axis (caught during H5 smoke testing: a
    drift check over only the last 3 rows was recomputing its own
    zero-point from those 3 rows alone, producing a completely different
    x-axis than the original fit and triggering false MODEL_STALE flags).
    """
    reference = get_reference_baseline(db, organization_id=organization_id, sensor=sensor, feature_type=feature_type)
    if reference is not None:
        return reference.source_window_start

    earliest = db.execute(
        select(HUMSFeature)
        .where(HUMSFeature.organization_id == organization_id, HUMSFeature.sensor_id == sensor.id, HUMSFeature.feature_type == feature_type)
        .order_by(HUMSFeature.window_end.asc())
    ).scalars().first()
    return earliest.window_end if earliest else None


def build_usage_trajectory(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, feature_rows: list[HUMSFeature],
    sensor: HUMSSensor | None = None, feature_type: str | None = None,
) -> tuple[list[float], str]:
    """Returns (usage_values, usage_unit) aligned 1:1 with feature_rows
    (chronological). Prefers FLIGHT_HOURS (reusing existing Flight/
    AssetHistoricalBaseline architecture) when the asset has any flight
    records; otherwise falls back to HOURS_ELAPSED (wall-clock), which is
    honestly a lower-fidelity usage proxy -- never silently presented as
    flight hours.

    `sensor`/`feature_type` are required for the HOURS_ELAPSED fallback so
    the zero-point can be resolved via `get_usage_anchor` (fixed,
    reproducible) rather than "whichever row happens to be first in
    `feature_rows`" — callers passing a partial row subset (e.g. a
    drift-check window) would otherwise silently get a different axis than
    the original model fit. If omitted, falls back to the old
    first-row-in-this-call behavior (only safe when `feature_rows` is
    always the FULL trajectory, never a subset).
    """
    has_flights = db.execute(select(Flight.id).where(Flight.organization_id == organization_id, Flight.asset_id == asset_id).limit(1)).first() is not None

    if has_flights:
        usage = [_usage_hours_asof(db, organization_id=organization_id, asset_id=asset_id, asof=r.window_end) for r in feature_rows]
        return usage, "FLIGHT_HOURS"

    if not feature_rows:
        return [], "HOURS_ELAPSED"

    t0 = None
    if sensor is not None and feature_type is not None:
        t0 = get_usage_anchor(db, organization_id=organization_id, sensor=sensor, feature_type=feature_type)
    if t0 is None:
        t0 = feature_rows[0].window_end
    usage = [round((r.window_end - t0).total_seconds() / 3600.0, 4) for r in feature_rows]
    return usage, "HOURS_ELAPSED"


def get_current_model(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, feature_type: str) -> HUMSDegradationModel | None:
    return db.execute(
        select(HUMSDegradationModel).where(
            HUMSDegradationModel.organization_id == organization_id,
            HUMSDegradationModel.sensor_id == sensor_id,
            HUMSDegradationModel.feature_type == feature_type,
            HUMSDegradationModel.is_current.is_(True),
        )
    ).scalar_one_or_none()


def fit_and_persist_model(
    db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, feature_type: str
) -> HUMSDegradationModel | None:
    """Fits (or refits) a degradation model from bounded recent feature
    history and persists a new version. Returns None if there isn't enough
    history to fit anything at all (caller must treat this as
    INSUFFICIENT_DATA, never fabricate a trajectory).
    """
    rows = list(
        db.execute(
            select(HUMSFeature)
            .where(
                HUMSFeature.organization_id == organization_id,
                HUMSFeature.sensor_id == sensor.id,
                HUMSFeature.feature_type == feature_type,
                HUMSFeature.quality.in_(("GOOD", "DEGRADED")),
            )
            .order_by(HUMSFeature.window_end.desc())
            .limit(MAX_TRAJECTORY_POINTS)
        )
        .scalars()
        .all()
    )
    rows.reverse()  # chronological

    reference = get_reference_baseline(db, organization_id=organization_id, sensor=sensor, feature_type=feature_type)
    if reference is not None:
        rows = [r for r in rows if r.window_end >= reference.source_window_start]

    if len(rows) < MIN_SAMPLES_FOR_DEGRADATION:
        return None

    usage, usage_unit = build_usage_trajectory(db, organization_id=organization_id, asset_id=sensor.asset_id, feature_rows=rows, sensor=sensor, feature_type=feature_type)
    values = [r.value for r in rows]

    selection = select_model(usage, values)
    if selection.fit is None:
        return None

    direction = degrading_direction(feature_type)
    trajectory_state = determine_trajectory_state(selection.fit, values, direction)

    usage_span = max(usage) - min(usage) if usage else 0.0
    if selection.fit.r_squared >= 0.8 and usage_span >= 10.0:
        quality, confidence = "HIGH", "HIGH"
    elif selection.fit.r_squared >= 0.5:
        quality, confidence = "MEDIUM", "MEDIUM"
    else:
        quality, confidence = "LOW", "LOW"

    existing = get_current_model(db, organization_id=organization_id, sensor_id=sensor.id, feature_type=feature_type)
    next_version = (existing.version + 1) if existing else 1
    if existing:
        existing.is_current = False

    model = HUMSDegradationModel(
        organization_id=organization_id,
        asset_id=sensor.asset_id,
        component_id=sensor.component_id,
        sensor_id=sensor.id,
        feature_type=feature_type,
        reference_baseline_id=reference.id if reference else None,
        model_type=selection.model_type,
        model_version=DEGRADATION_MODEL_VERSION,
        fit_slope=selection.fit.slope,
        fit_intercept=selection.fit.intercept,
        fit_error=selection.fit.fit_error,
        r_squared=selection.fit.r_squared,
        sample_count=selection.fit.sample_count,
        usage_unit=usage_unit,
        usage_span=usage_span,
        trajectory_state=trajectory_state,
        quality=quality,
        confidence=confidence,
        version=next_version,
        is_current=True,
    )
    db.add(model)
    db.flush()
    return model


__all__ = [
    "degrading_direction",
    "get_reference_baseline",
    "build_usage_trajectory",
    "get_current_model",
    "fit_and_persist_model",
    "DEGRADING_UPWARD_FEATURES",
]
