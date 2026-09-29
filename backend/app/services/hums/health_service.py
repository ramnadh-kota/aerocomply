"""H3: Orchestrates baseline_service + health_engine into feature/component/
asset health results, and integrates meaningful deterioration into the
existing ProactiveSignalRecord (no second alert system — see H1/H2's own
`hums_service._sync_exceedance_signal` for the established pattern this
mirrors).

Performance note: every function here queries a bounded, indexed slice of
HUMSFeature (see FEATURE_HISTORY_LIMIT) plus at most one HUMSBaseline row
per (sensor, feature_type) — never a full historical scan. See
docs/HUMS_BASELINE_ENGINE.md's performance section.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hums import HUMSBaseline, HUMSFeature, HUMSSensor
from app.models.proactive_signal import ProactiveSignalRecord
from app.services.hums import baseline_service
from app.services.hums.baseline_engine import BaselineStats
from app.services.hums.health_engine import (
    AggregateHealthResult,
    FeatureHealthResult,
    aggregate_health,
    compute_deviation,
    compute_trend,
    consecutive_deviation_count,
    determine_feature_health,
)

# Which feature_type(s) drive health evaluation for a given sensor
# measurement_type. Vibration gets three contributors (level + two shape
# features); everything else evaluates its "mean" level feature. This is
# the extension point for adding a new measurement_type's health features.
HEALTH_FEATURES_BY_MEASUREMENT_TYPE: dict[str, list[str]] = {
    "vibration": ["rms", "crest_factor", "kurtosis"],
}
DEFAULT_HEALTH_FEATURE = "mean"

FEATURE_HISTORY_LIMIT = 50


def _baseline_stats_from_row(row: HUMSBaseline | None) -> BaselineStats | None:
    if row is None:
        return None
    return BaselineStats(
        sample_count=row.sample_count, mean=row.mean, median=row.median, std_dev=row.std_dev,
        minimum=row.minimum, maximum=row.maximum,
        percentile_05=row.percentile_05, percentile_25=row.percentile_25, percentile_50=row.percentile_50,
        percentile_75=row.percentile_75, percentile_95=row.percentile_95,
        lower_bound=row.lower_bound, upper_bound=row.upper_bound,
        quality=row.quality, confidence=row.confidence, calculation_method=row.calculation_method,
    )


def _feature_history(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, feature_type: str) -> list[HUMSFeature]:
    rows = list(
        db.execute(
            select(HUMSFeature)
            .where(
                HUMSFeature.organization_id == organization_id,
                HUMSFeature.sensor_id == sensor_id,
                HUMSFeature.feature_type == feature_type,
                HUMSFeature.quality.in_(("GOOD", "DEGRADED")),
            )
            .order_by(HUMSFeature.window_end.desc())
            .limit(FEATURE_HISTORY_LIMIT)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))  # chronological


def refresh_baselines_after_ingestion(
    db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, persisted_features: list[HUMSFeature]
) -> None:
    """Called once per ingested batch (from hums_service.detect_and_record_
    exceedances, right after feature_service.process_window persists the new
    HUMSFeature rows) — NOT called on every health-intelligence read. This
    is what keeps baseline recomputation bounded to ingestion rate rather
    than request rate (H3 spec section 33's performance requirement).

    Recomputes the baseline for each health-relevant feature_type that was
    just persisted, using feature history that EXCLUDES the rows just
    inserted in this batch — a baseline must represent PRIOR expected
    behavior, never absorb the very observation it will next be compared
    against (an anomaly would otherwise widen its own "normal" range and
    could never be detected).
    """
    relevant_types = HEALTH_FEATURES_BY_MEASUREMENT_TYPE.get(sensor.measurement_type, [DEFAULT_HEALTH_FEATURE])
    newly_persisted_ids = {f.id for f in persisted_features}
    newly_persisted_types = {f.feature_type for f in persisted_features}

    for feature_type in relevant_types:
        if feature_type not in newly_persisted_types:
            continue
        prior_history = list(
            db.execute(
                select(HUMSFeature)
                .where(
                    HUMSFeature.organization_id == organization_id,
                    HUMSFeature.sensor_id == sensor.id,
                    HUMSFeature.feature_type == feature_type,
                    HUMSFeature.quality.in_(("GOOD", "DEGRADED")),
                    HUMSFeature.id.notin_(newly_persisted_ids),
                )
                .order_by(HUMSFeature.window_end.desc())
                .limit(baseline_service.BASELINE_HISTORY_LIMIT)
            )
            .scalars()
            .all()
        )
        if not prior_history:
            continue  # first-ever batch for this feature: no prior data to baseline from yet
        baseline_service.get_or_compute_baseline(
            db, organization_id=organization_id, sensor=sensor, feature_type=feature_type, history_override=prior_history
        )


def evaluate_feature_health(
    db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, feature_type: str
) -> FeatureHealthResult:
    history = _feature_history(db, organization_id=organization_id, sensor_id=sensor.id, feature_type=feature_type)

    if not history:
        deviation = compute_deviation(0.0, None)
        trend = compute_trend([], [])
        return determine_feature_health(feature_type=feature_type, deviation=deviation, trend=trend, consecutive_count=0)

    # Read-only: baselines are (re)computed at ingestion time by
    # refresh_baselines_after_ingestion above, never recomputed on a read.
    baseline_row = baseline_service.get_current_baseline(db, organization_id=organization_id, sensor_id=sensor.id, feature_type=feature_type)
    baseline_stats = _baseline_stats_from_row(baseline_row)

    values = [h.value for h in history]
    t0 = history[0].window_end
    timestamps_seconds = [(h.window_end - t0).total_seconds() for h in history]

    deviation = compute_deviation(values[-1], baseline_stats)
    trend = compute_trend(values, timestamps_seconds)
    consecutive = consecutive_deviation_count(values, baseline_stats)

    return determine_feature_health(feature_type=feature_type, deviation=deviation, trend=trend, consecutive_count=consecutive)


def evaluate_sensor_health(db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor) -> list[FeatureHealthResult]:
    feature_types = HEALTH_FEATURES_BY_MEASUREMENT_TYPE.get(sensor.measurement_type, [DEFAULT_HEALTH_FEATURE])
    return [evaluate_feature_health(db, organization_id=organization_id, sensor=sensor, feature_type=ft) for ft in feature_types]


def evaluate_component_health(
    db: Session, *, organization_id: uuid.UUID, sensors: list[HUMSSensor]
) -> tuple[AggregateHealthResult, list[FeatureHealthResult]]:
    all_results: list[FeatureHealthResult] = []
    for sensor in sensors:
        all_results.extend(evaluate_sensor_health(db, organization_id=organization_id, sensor=sensor))
    return aggregate_health(all_results), all_results


def sync_health_signal(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, component_id: uuid.UUID | None,
    aggregate: AggregateHealthResult, label: str,
) -> None:
    """Creates/refreshes a ProactiveSignalRecord for meaningful (DEGRADED+)
    deterioration — never for HEALTHY/WATCH, so normal variation doesn't
    spam the signal feed (per H3 spec section 20).
    """
    if aggregate.state not in ("DEGRADED", "WARNING", "CRITICAL"):
        return

    key = f"hums_health:{asset_id}:{component_id or 'asset'}:{aggregate.state}"
    existing = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.organization_id == organization_id,
            ProactiveSignalRecord.signal_key == key,
        )
    ).scalar_one_or_none()
    if existing and existing.status in ("OPEN", "ACKNOWLEDGED", "IN_REVIEW"):
        return  # already open for this exact (scope, state) — avoid duplicate noise

    severity = {"DEGRADED": "MEDIUM", "WARNING": "HIGH", "CRITICAL": "CRITICAL"}[aggregate.state]
    contributor_lines = []
    for c in aggregate.primary_contributors[:3]:
        contributor_lines.extend(c.explanation)

    record = ProactiveSignalRecord(
        organization_id=organization_id,
        signal_key=key,
        signal_type="HUMS_HEALTH_DEGRADATION",
        severity=severity,
        priority=severity,
        status="OPEN",
        title=f"HUMS Health {aggregate.state.title()} — {label}",
        headline=f"{label} health intelligence reports {aggregate.state} based on {len(aggregate.primary_contributors)} contributing feature(s).",
        explanation_json=contributor_lines or [f"{label} health state is {aggregate.state}."],
        asset_id=asset_id,
        component_id=component_id,
        detected_at=datetime.datetime.now(datetime.UTC),
        evidence_json=[],
        contributing_factors_json={
            "health_state": aggregate.state,
            "confidence": aggregate.confidence,
            "primary_contributors": [c.feature_type for c in aggregate.primary_contributors],
        },
        recommended_actions_json=[
            {
                "action_type": "MONITOR_ASSET",
                "title": "Review HUMS Health Intelligence",
                "description": f"Investigate {label}'s degrading feature(s): {', '.join(c.feature_type for c in aggregate.primary_contributors[:3])}.",
                "target_url": f"/assets/{asset_id}",
                "requires_authorization": aggregate.state == "CRITICAL",
            }
        ],
    )
    db.add(record)


__all__ = [
    "evaluate_feature_health",
    "evaluate_sensor_health",
    "evaluate_component_health",
    "sync_health_signal",
    "HEALTH_FEATURES_BY_MEASUREMENT_TYPE",
    "DEFAULT_HEALTH_FEATURE",
]
