"""H5: Threshold sourcing, RUL computation, and persisted
HUMSPrognosticRecord — the DB-touching orchestrator that ties
degradation_engine + degradation_service into a result, links the H4
diagnostic candidate that motivated the evaluation (if any), and
integrates meaningful RUL transitions into the existing
ProactiveSignalRecord (no second alert system).

Every RUL value produced here is an ESTIMATE, NOT A CERTIFIED LIFE LIMIT —
see docs/HUMS_PROGNOSTICS.md's safety-boundary section. Nothing in this
module grounds an asset, declares airworthiness, or approves maintenance.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hums import HUMSDegradationModel, HUMSDiagnosticCandidate, HUMSFeature, HUMSPrognosticRecord, HUMSSensor
from app.models.proactive_signal import ProactiveSignalRecord
from app.services.hums import degradation_service
from app.services.hums.degradation_engine import compute_rul, detect_model_drift

# Demo/placeholder thresholds distinguished by TYPE (never presented as an
# OEM/regulatory limit). "rms" reuses H1's own configured vibration
# maintenance threshold (hums_service.VIBRATION_CRITICAL_RMS) so H5's
# threshold is literally the same constant H1's exceedance pathway already
# uses -- one configured value, two consumers, not two competing numbers.
_MAINTENANCE_THRESHOLD_FEATURE_TYPES = {"rms"}


def _get_threshold(feature_type: str, reference_mean: float | None) -> tuple[float | None, str | None]:
    if feature_type in _MAINTENANCE_THRESHOLD_FEATURE_TYPES:
        from app.services import hums_service  # local import: avoids a hums_service <-> app.services.hums import cycle

        return hums_service.VIBRATION_CRITICAL_RMS, "MAINTENANCE_THRESHOLD"

    if reference_mean is not None:
        # No configured maintenance threshold exists for this feature_type --
        # fall back to a documented multiple of the reference baseline mean,
        # explicitly typed CONFIGURED_PROGNOSTIC_THRESHOLD (never
        # ENGINEERING_LIMIT/MAINTENANCE_THRESHOLD) so a caller can never
        # mistake it for an approved engineering limit.
        return round(abs(reference_mean) * 2.0, 6), "CONFIGURED_PROGNOSTIC_THRESHOLD"

    return None, None


def get_current_prognostic(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, feature_type: str) -> HUMSPrognosticRecord | None:
    return db.execute(
        select(HUMSPrognosticRecord).where(
            HUMSPrognosticRecord.organization_id == organization_id,
            HUMSPrognosticRecord.sensor_id == sensor_id,
            HUMSPrognosticRecord.feature_type == feature_type,
            HUMSPrognosticRecord.is_current.is_(True),
        )
    ).scalar_one_or_none()


def _find_related_diagnostic(db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor) -> HUMSDiagnosticCandidate | None:
    """Links the strongest non-rejected H4 candidate touching this sensor,
    if any -- preserved as CONTEXT/input uncertainty, never treated as a
    confirmed failure mode (H5 spec section 26)."""
    return db.execute(
        select(HUMSDiagnosticCandidate)
        .where(
            HUMSDiagnosticCandidate.organization_id == organization_id,
            HUMSDiagnosticCandidate.asset_id == sensor.asset_id,
            HUMSDiagnosticCandidate.status.notin_(("REJECTED",)),
        )
        .order_by(HUMSDiagnosticCandidate.score.desc())
    ).scalars().first()


def evaluate_and_persist_prognostic(
    db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, feature_type: str
) -> HUMSPrognosticRecord:
    model = degradation_service.fit_and_persist_model(db, organization_id=organization_id, sensor=sensor, feature_type=feature_type)

    latest_feature = db.execute(
        select(HUMSFeature)
        .where(
            HUMSFeature.organization_id == organization_id, HUMSFeature.sensor_id == sensor.id,
            HUMSFeature.feature_type == feature_type, HUMSFeature.quality.in_(("GOOD", "DEGRADED")),
        )
        .order_by(HUMSFeature.window_end.desc())
    ).scalars().first()

    now = datetime.datetime.now(datetime.UTC)
    current_value = latest_feature.value if latest_feature else 0.0
    observed_at = latest_feature.window_end if latest_feature else now

    existing = get_current_prognostic(db, organization_id=organization_id, sensor_id=sensor.id, feature_type=feature_type)

    if model is None or latest_feature is None:
        record = _upsert_prognostic(
            db, organization_id=organization_id, sensor=sensor, feature_type=feature_type, existing=existing,
            current_value=current_value, threshold_value=None, threshold_type=None,
            rul=None, rul_lower=None, rul_upper=None, rul_unit=None, extrapolation_distance=None,
            confidence="INSUFFICIENT_DATA", quality="INSUFFICIENT_DATA", status="INSUFFICIENT_DATA",
            explanation=["Not enough feature history yet to fit a degradation trajectory."],
            degradation_model_id=None, observed_at=observed_at, calculated_at=now,
        )
        return record

    from app.services.hums.baseline_service import get_current_baseline

    baseline = get_current_baseline(db, organization_id=organization_id, sensor_id=sensor.id, feature_type=feature_type)
    reference_mean = baseline.mean if baseline else None
    threshold_value, threshold_type = _get_threshold(feature_type, reference_mean)

    direction = degradation_service.degrading_direction(feature_type)
    fit = _fit_from_model_row(model)

    recent_rows = list(
        db.execute(
            select(HUMSFeature)
            .where(HUMSFeature.organization_id == organization_id, HUMSFeature.sensor_id == sensor.id, HUMSFeature.feature_type == feature_type)
            .order_by(HUMSFeature.window_end.desc())
            .limit(3)
        )
        .scalars()
        .all()
    )
    recent_usage, _ = degradation_service.build_usage_trajectory(
        db, organization_id=organization_id, asset_id=sensor.asset_id, feature_rows=list(reversed(recent_rows)),
        sensor=sensor, feature_type=feature_type,
    )
    is_stale = detect_model_drift(fit, recent_usage, [r.value for r in reversed(recent_rows)]) if recent_usage else False

    if threshold_value is None:
        rul_status = "LIMITED"
        rul_explanation = ["No threshold could be determined for this feature -- RUL cannot be computed without one."]
        rul_result = None
    else:
        current_usage = recent_usage[-1] if recent_usage else 0.0
        rul_result = compute_rul(fit, current_usage=current_usage, threshold_value=threshold_value, degrading_direction=direction, observed_usage_span=model.usage_span)
        rul_explanation = list(rul_result.explanation)
        if is_stale:
            rul_status = "STALE"
            rul_explanation.append("MODEL_STALE: recent observations deviate substantially from the fitted trajectory -- this estimate may no longer represent current behavior.")
        elif rul_result.rul_point is None:
            rul_status = "LIMITED"
        elif rul_result.is_low_confidence_extrapolation:
            rul_status = "LOW_CONFIDENCE"
        else:
            rul_status = "AVAILABLE"

    related_diagnostic = _find_related_diagnostic(db, organization_id=organization_id, sensor=sensor)
    if related_diagnostic:
        rul_explanation.append(
            f"Related H4 diagnostic hypothesis: '{related_diagnostic.fault_name}' (status={related_diagnostic.status}, "
            f"confidence={related_diagnostic.confidence}) -- treated as contextual input uncertainty, not a confirmed failure mode."
        )
    rul_explanation.append("ESTIMATE — NOT A CERTIFIED LIFE LIMIT.")

    record = _upsert_prognostic(
        db, organization_id=organization_id, sensor=sensor, feature_type=feature_type, existing=existing,
        current_value=current_value, threshold_value=threshold_value, threshold_type=threshold_type,
        rul=rul_result.rul_point if rul_result else None,
        rul_lower=rul_result.rul_lower if rul_result else None,
        rul_upper=rul_result.rul_upper if rul_result else None,
        rul_unit=model.usage_unit if rul_result and rul_result.rul_point is not None else None,
        extrapolation_distance=rul_result.extrapolation_distance if rul_result else None,
        confidence="STALE" if is_stale else (rul_result.confidence if rul_result else "INSUFFICIENT_DATA"),
        quality=model.quality if not is_stale else "STALE",
        status=rul_status,
        explanation=rul_explanation,
        degradation_model_id=model.id,
        diagnostic_candidate_id=related_diagnostic.id if related_diagnostic else None,
        observed_at=observed_at, calculated_at=now,
    )

    _sync_rul_signal(db, organization_id=organization_id, record=record, sensor=sensor)
    return record


def _fit_from_model_row(model: HUMSDegradationModel):
    from app.services.hums.degradation_engine import LinearFit

    # usage_mean/usage_sum_sq_dev aren't persisted (derivable inputs, not
    # independent facts) -- reconstructed as 0/sample_count*usage_span^2
    # would be inexact, so the prediction-interval leverage term uses a
    # conservative approximation here (mean=0, spread=usage_span^2) rather
    # than the exact original values. Documented in docs/HUMS_RUL_ENGINE.md.
    return LinearFit(
        slope=model.fit_slope, intercept=model.fit_intercept, fit_error=model.fit_error, r_squared=model.r_squared,
        residual_std=model.fit_error, sample_count=model.sample_count, usage_mean=0.0,
        usage_sum_sq_dev=max(1e-6, model.usage_span**2),
    )


def _upsert_prognostic(
    db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor, feature_type: str, existing: HUMSPrognosticRecord | None,
    current_value: float, threshold_value: float | None, threshold_type: str | None,
    rul: float | None, rul_lower: float | None, rul_upper: float | None, rul_unit: str | None,
    extrapolation_distance: float | None, confidence: str, quality: str, status: str, explanation: list[str],
    degradation_model_id: uuid.UUID | None, diagnostic_candidate_id: uuid.UUID | None = None,
    observed_at: datetime.datetime, calculated_at: datetime.datetime,
) -> HUMSPrognosticRecord:
    next_version = (existing.version + 1) if existing else 1
    if existing:
        existing.is_current = False

    record = HUMSPrognosticRecord(
        organization_id=organization_id, asset_id=sensor.asset_id, component_id=sensor.component_id, sensor_id=sensor.id,
        feature_type=feature_type, degradation_model_id=degradation_model_id, diagnostic_candidate_id=diagnostic_candidate_id,
        current_value=current_value, threshold_value=threshold_value, threshold_type=threshold_type,
        rul_estimate=rul, rul_lower=rul_lower, rul_upper=rul_upper, rul_unit=rul_unit,
        extrapolation_distance=extrapolation_distance, confidence=confidence, quality=quality, status=status,
        explanation=explanation, observed_at=observed_at, calculated_at=calculated_at, version=next_version, is_current=True,
    )
    db.add(record)
    db.flush()
    return record


# RUL is considered to have entered the "warning window" when the point
# estimate drops below this many usage-units of remaining life -- a
# demo/placeholder constant (documented, not an engineering-derived value).
_RUL_WARNING_WINDOW = 50.0


def _sync_rul_signal(db: Session, *, organization_id: uuid.UUID, record: HUMSPrognosticRecord, sensor: HUMSSensor) -> None:
    """Only emits a signal for a MEANINGFUL transition (per spec section
    32) -- entering the warning window, or LOW_CONFIDENCE/STALE status --
    never on every recomputed RUL value. Dedup key includes the coarse
    bucket so a 1-hour RUL change never re-triggers.
    """
    if record.status not in ("LOW_CONFIDENCE", "STALE") and not (record.rul_estimate is not None and record.rul_estimate <= _RUL_WARNING_WINDOW):
        return

    bucket = record.status if record.status in ("LOW_CONFIDENCE", "STALE") else "WARNING_WINDOW"
    key = f"hums_rul:{sensor.id}:{record.feature_type}:{bucket}"
    existing_signal = db.execute(
        select(ProactiveSignalRecord).where(ProactiveSignalRecord.organization_id == organization_id, ProactiveSignalRecord.signal_key == key)
    ).scalar_one_or_none()
    if existing_signal and existing_signal.status in ("OPEN", "ACKNOWLEDGED", "IN_REVIEW"):
        return

    severity = "HIGH" if bucket == "WARNING_WINDOW" else "MEDIUM"
    rul_text = f"{record.rul_estimate} {record.rul_unit} (range {record.rul_lower}-{record.rul_upper})" if record.rul_estimate is not None else "unavailable"
    signal = ProactiveSignalRecord(
        organization_id=organization_id,
        signal_key=key,
        signal_type="HUMS_RUL_WARNING",
        severity=severity,
        priority=severity,
        status="OPEN",
        title=f"HUMS RUL {bucket.replace('_', ' ').title()} — Sensor {sensor.sensor_code}",
        headline=f"Estimated remaining useful life for {record.feature_type} on sensor {sensor.sensor_code}: {rul_text}.",
        explanation_json=record.explanation,
        asset_id=record.asset_id,
        component_id=record.component_id,
        detected_at=datetime.datetime.now(datetime.UTC),
        evidence_json=[],
        contributing_factors_json={"prognostic_id": str(record.id), "status": record.status, "confidence": record.confidence},
        recommended_actions_json=[
            {
                "action_type": "MONITOR_ASSET",
                "title": "Review Prognostic Estimate",
                "description": f"Review the RUL estimate for sensor {sensor.sensor_code} and plan inspection/maintenance accordingly. This is a prognostic estimate, not a certified life limit.",
                "target_url": f"/assets/{record.asset_id}",
                "requires_authorization": True,
            }
        ],
    )
    db.add(signal)


__all__ = ["evaluate_and_persist_prognostic", "get_current_prognostic"]
