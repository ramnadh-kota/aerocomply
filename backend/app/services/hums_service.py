"""H1 + H2: HUMS foundation and health/exceedance evaluation service.

Implements the pathway:
    Sensor Reading -> Feature Engine (app.services.hums) -> Exceedance -> Finding -> Evidence -> Signal

H1 implemented one feature (vibration RMS) and one threshold rule inline.
H2 (see app/services/hums/) added a real feature-processing engine —
validation, preprocessing, time-domain, frequency-domain (DFT), and
domain-specific (trend) features, all persisted as traceable HUMSFeature
rows. This module no longer duplicates the RMS formula: it calls the same
app.services.hums.feature_extractors functions the persisted-feature engine
uses, and persists the full feature set on every ingested batch via
app.services.hums.feature_service.process_window.

Diagnostics (fault isolation/classification), prognostics (degradation
modeling, RUL), and the digital twin state layer are still NOT part of this
codebase — see docs/HUMS_ARCHITECTURE.md for what is scaffolded vs. real.

Nothing here fabricates a health score, diagnosis, or RUL value: when there
is insufficient data, functions return INSUFFICIENT_DATA / null rather than
inventing a number (same invariant M7's proactive_intelligence_service and
the Kleene-logic compliance model already enforce elsewhere in this codebase).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.asset import Asset
from app.models.component import Component
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.hums import HUMSDegradationModel, HUMSExceedance, HUMSFeature, HUMSPrognosticRecord, HUMSSensor, HUMSSensorReading
from app.models.proactive_signal import ProactiveSignalRecord
from app.schemas.hums import (
    HUMSAssetHealthIntelligence,
    HUMSAssetHealthSummary,
    HUMSBaselineResponse,
    HUMSComponentHealth,
    HUMSComponentHealthIntelligence,
    HUMSDeviationResponse,
    HUMSExceedanceResponse,
    HUMSFeatureHealthResponse,
    HUMSFeatureValue,
    HUMSReadingIn,
    HUMSSensorCreate,
    HUMSTrendResponse,
)
from app.schemas.intelligence_signal import SignalEvidenceRef
from app.services import audit_service
from app.services.hums import baseline_service, degradation_service, diagnostic_service, feature_service, health_service, prognostic_service
from app.services.hums.feature_extractors import vibration_time_domain_features
from app.services.hums.health_engine import FeatureHealthResult
import structlog

log = structlog.get_logger(__name__)

# Vibration RMS thresholds (mm/s). Not asset-model-specific yet — a single
# fleet-wide baseline, documented here rather than hidden in a magic number,
# consistent with the spec's "document threshold/baseline calculation
# methods" requirement. Real thresholds would come from OEM limits per
# component type; this is a deliberately simple placeholder for the slice.
VIBRATION_WARNING_RMS = 5.0
VIBRATION_CRITICAL_RMS = 8.0
FEATURE_WINDOW_READING_COUNT = 20
MIN_READINGS_FOR_HEALTH = 5


def create_sensor(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID | None, payload: HUMSSensorCreate
) -> HUMSSensor:
    # Tenant integrity: the asset (and component) must belong to the caller's organization. Without this a tenant
    # could attach sensors to another tenant's asset id.
    if db.execute(select(Asset.id).where(Asset.id == payload.asset_id, Asset.organization_id == organization_id,
                                         Asset.deleted_at.is_(None))).first() is None:
        raise NotFoundError("Asset not found")
    if payload.component_id is not None and db.execute(
        select(Component.id).where(Component.id == payload.component_id, Component.organization_id == organization_id)
    ).first() is None:
        raise NotFoundError("Component not found")
    sensor = HUMSSensor(
        organization_id=organization_id,
        asset_id=payload.asset_id,
        component_id=payload.component_id,
        sensor_code=payload.sensor_code,
        sensor_type=payload.sensor_type,
        measurement_type=payload.measurement_type,
        unit=payload.unit,
        installation_location=payload.installation_location,
        source=payload.source,
    )
    db.add(sensor)
    db.flush()
    audit_service.record_audit_event(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action="hums_sensor.created",
        entity_type="HUMSSensor",
        entity_id=sensor.id,
        metadata={"asset_id": str(sensor.asset_id), "sensor_type": sensor.sensor_type},
    )
    return sensor


def list_sensors(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID | None = None) -> list[HUMSSensor]:
    query = select(HUMSSensor).where(HUMSSensor.organization_id == organization_id)
    if asset_id:
        query = query.where(HUMSSensor.asset_id == asset_id)
    return list(db.execute(query).scalars().all())


def vibration_limits(sensor: HUMSSensor) -> tuple[float, float, str]:
    """(warning, critical, source) RMS limits for a sensor: its configured limits, else the platform defaults.
    The defaults are generic starting values and are NOT an OEM or regulatory limit."""
    if sensor.warning_threshold is not None and sensor.critical_threshold is not None:
        return sensor.warning_threshold, sensor.critical_threshold, "CONFIGURED"
    return VIBRATION_WARNING_RMS, VIBRATION_CRITICAL_RMS, "PLATFORM_DEFAULT"


def set_sensor_thresholds(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID | None, sensor_id: uuid.UUID,
    warning_threshold: float | None, critical_threshold: float | None,
) -> HUMSSensor:
    sensor = _get_sensor(db, organization_id=organization_id, sensor_id=sensor_id)
    previous = {"warning_threshold": sensor.warning_threshold, "critical_threshold": sensor.critical_threshold}
    sensor.warning_threshold, sensor.critical_threshold = warning_threshold, critical_threshold
    db.flush()
    audit_service.record_audit_event(
        db, organization_id=organization_id, user_id=user_id, action="hums_sensor.thresholds_set",
        entity_type="HUMSSensor", entity_id=sensor.id,
        metadata={"previous": previous, "new": {"warning_threshold": warning_threshold,
                                                "critical_threshold": critical_threshold}},
    )
    return sensor


def _get_sensor(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID) -> HUMSSensor:
    sensor = db.execute(
        select(HUMSSensor).where(HUMSSensor.id == sensor_id, HUMSSensor.organization_id == organization_id)
    ).scalar_one_or_none()
    if not sensor:
        raise NotFoundError("Sensor not found", code="hums_sensor_not_found")
    return sensor


def ingest_readings(
    db: Session,
    *,
    organization_id: uuid.UUID,
    sensor_id: uuid.UUID,
    readings: list[HUMSReadingIn],
    ingestion_batch: str | None,
) -> list[HUMSSensorReading]:
    sensor = _get_sensor(db, organization_id=organization_id, sensor_id=sensor_id)
    created: list[HUMSSensorReading] = []
    for r in readings:
        row = HUMSSensorReading(
            organization_id=organization_id,
            sensor_id=sensor.id,
            asset_id=sensor.asset_id,
            flight_id=r.flight_id,
            recorded_at=r.recorded_at,
            value=r.value,
            unit=r.unit,
            data_quality=r.data_quality,
            source=sensor.source,
            ingestion_batch=ingestion_batch,
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def _compute_rms_feature(readings: list[HUMSSensorReading]) -> HUMSFeatureValue | None:
    """Delegates to app.services.hums.feature_extractors.vibration_time_domain_features
    (the H2 feature engine's own RMS formula) rather than a second inline
    implementation — see that module's `rms` calculation ("sqrt(mean(x^2))").
    """
    valid = [r for r in readings if r.data_quality == "VALID"]
    if len(valid) < MIN_READINGS_FOR_HEALTH:
        return None
    values = [r.value for r in valid]
    rms_result = vibration_time_domain_features(values, valid[0].unit)["rms"]
    if rms_result.value is None:
        return None
    return HUMSFeatureValue(
        parameter="vibration_rms",
        value=rms_result.value,
        unit=valid[0].unit,
        window_start=min(r.recorded_at for r in valid),
        window_end=max(r.recorded_at for r in valid),
        sample_count=len(valid),
    )


def _latest_readings(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID) -> list[HUMSSensorReading]:
    return list(
        db.execute(
            select(HUMSSensorReading)
            .where(
                HUMSSensorReading.organization_id == organization_id,
                HUMSSensorReading.sensor_id == sensor_id,
            )
            .order_by(HUMSSensorReading.recorded_at.desc())
            .limit(FEATURE_WINDOW_READING_COUNT)
        )
        .scalars()
        .all()
    )


def evaluate_sensor_health(
    db: Session, *, organization_id: uuid.UUID, sensor: HUMSSensor
) -> HUMSComponentHealth:
    """Computes a feature + health indicator for one sensor. Never fabricates
    a score: returns INSUFFICIENT_DATA when fewer than MIN_READINGS_FOR_HEALTH
    valid readings exist.
    """
    readings = _latest_readings(db, organization_id=organization_id, sensor_id=sensor.id)
    feature = _compute_rms_feature(readings) if sensor.measurement_type == "vibration" else None

    active_exceedances = db.execute(
        select(HUMSExceedance).where(
            HUMSExceedance.organization_id == organization_id,
            HUMSExceedance.sensor_id == sensor.id,
        )
    ).scalars().all()

    if feature is None:
        return HUMSComponentHealth(
            sensor_id=sensor.id,
            parameter="vibration_rms" if sensor.measurement_type == "vibration" else sensor.measurement_type,
            health_score=None,
            status="INSUFFICIENT_DATA",
            latest_feature=None,
            active_exceedance_count=len(active_exceedances),
            confidence="INSUFFICIENT_DATA",
        )

    warn_limit, crit_limit, _limit_source = vibration_limits(sensor)
    if feature.value >= crit_limit:
        status = "CRITICAL"
        health_score = max(0.0, 40.0 - (feature.value - crit_limit) * 10)
    elif feature.value >= warn_limit:
        status = "DEGRADED"
        span = crit_limit - warn_limit
        health_score = 40.0 + (1 - (feature.value - warn_limit) / span) * 40.0
    else:
        status = "HEALTHY"
        health_score = 80.0 + (1 - feature.value / warn_limit) * 20.0

    confidence = "HIGH" if feature.sample_count >= FEATURE_WINDOW_READING_COUNT else "MEDIUM"

    return HUMSComponentHealth(
        sensor_id=sensor.id,
        parameter=feature.parameter,
        health_score=round(health_score, 1),
        status=status,
        latest_feature=feature,
        active_exceedance_count=len(active_exceedances),
        confidence=confidence,
    )


def get_asset_health(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> HUMSAssetHealthSummary:
    sensors = list_sensors(db, organization_id=organization_id, asset_id=asset_id)
    components = [evaluate_sensor_health(db, organization_id=organization_id, sensor=s) for s in sensors]

    statuses = [c.status for c in components]
    if not components:
        overall = "INSUFFICIENT_DATA"
    elif "CRITICAL" in statuses:
        overall = "CRITICAL"
    elif "DEGRADED" in statuses:
        overall = "DEGRADED"
    elif all(s == "HEALTHY" for s in statuses):
        overall = "HEALTHY"
    else:
        overall = "INSUFFICIENT_DATA"

    return HUMSAssetHealthSummary(
        asset_id=asset_id,
        overall_status=overall,
        sensor_count=len(sensors),
        active_exceedance_count=sum(c.active_exceedance_count for c in components),
        components=components,
        generated_at=datetime.datetime.now(datetime.UTC),
    )


def detect_and_record_exceedances(
    db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, user_id: uuid.UUID | None
) -> HUMSExceedanceResponse | None:
    """Evaluates the sensor's latest feature against thresholds. On breach,
    creates the full Exceedance -> Finding -> Evidence -> Signal chain
    (idempotent: does nothing if an open exceedance already covers this
    reading window).
    """
    sensor = _get_sensor(db, organization_id=organization_id, sensor_id=sensor_id)
    # Serialise evaluation PER SENSOR for the rest of this transaction: two workers ingesting the same sensor at once
    # would otherwise both find "no exceedance for this window yet" and each create an exceedance + finding + evidence.
    db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(f"hums-eval:{sensor.id}", 0))))
    readings = _latest_readings(db, organization_id=organization_id, sensor_id=sensor.id)

    # H2: persist the full feature set (time-domain, frequency-domain,
    # domain-specific) for feature-history/trend queries on every ingested
    # batch, independent of whether a threshold is breached below.
    persisted_features = feature_service.process_window(db, sensor=sensor, readings=readings) if readings else []

    # H3: recompute health-relevant baselines from PRIOR history now that
    # this batch's features are persisted (bounded to ingestion rate, not
    # read rate -- see health_service.refresh_baselines_after_ingestion).
    if persisted_features:
        health_service.refresh_baselines_after_ingestion(
            db, organization_id=organization_id, sensor=sensor, persisted_features=persisted_features
        )

    if sensor.measurement_type.lower() not in ("vibration", "vib"):
        return None

    warn_limit, crit_limit, limit_source = vibration_limits(sensor)
    feature = _compute_rms_feature(readings)
    if feature is None or feature.value < warn_limit:
        return None

    severity = "CRITICAL" if feature.value >= crit_limit else "HIGH"
    threshold = crit_limit if severity == "CRITICAL" else warn_limit

    crest_factor_feature = feature_service.get_feature(persisted_features, "crest_factor")
    kurtosis_feature = feature_service.get_feature(persisted_features, "kurtosis")
    dominant_freq_feature = feature_service.get_feature(persisted_features, "dominant_frequency")

    existing = db.execute(
        select(HUMSExceedance).where(
            HUMSExceedance.organization_id == organization_id,
            HUMSExceedance.sensor_id == sensor.id,
            HUMSExceedance.window_end == feature.window_end,
        )
    ).scalar_one_or_none()
    if existing:
        return HUMSExceedanceResponse.model_validate(existing)

    valid_readings = [r for r in readings if r.data_quality == "VALID"]

    supporting_feature_notes = []
    if crest_factor_feature and crest_factor_feature.value is not None:
        supporting_feature_notes.append(f"crest factor {crest_factor_feature.value}")
    if kurtosis_feature and kurtosis_feature.value is not None:
        supporting_feature_notes.append(f"kurtosis {kurtosis_feature.value}")
    if dominant_freq_feature and dominant_freq_feature.value is not None:
        supporting_feature_notes.append(f"dominant frequency {dominant_freq_feature.value} Hz")
    supporting_suffix = f" Supporting features: {', '.join(supporting_feature_notes)}." if supporting_feature_notes else ""

    finding = Finding(
        organization_id=organization_id,
        asset_id=sensor.asset_id,
        component_id=sensor.component_id,
        title=f"Vibration Exceedance — Sensor {sensor.sensor_code}",
        description=(
            f"Vibration RMS reached {feature.value} {feature.unit} against a "
            f"{severity.lower()} threshold of {threshold} {feature.unit}, computed over "
            f"{feature.sample_count} samples between {feature.window_start.isoformat()} and "
            f"{feature.window_end.isoformat()}.{supporting_suffix}"
        ),
        severity=FindingSeverity.CRITICAL if severity == "CRITICAL" else FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
    )
    db.add(finding)
    db.flush()

    evidence = Evidence(
        organization_id=organization_id,
        asset_id=sensor.asset_id,
        finding_id=finding.id,
        title=f"HUMS Vibration Telemetry — {sensor.sensor_code}",
        description="Auto-generated from HUMS sensor readings supporting the vibration exceedance finding.",
        evidence_type="HUMS_TELEMETRY",
        source="hums_service.detect_and_record_exceedances",
        captured_at=feature.window_end,
        status=EvidenceStatus.SUBMITTED.value,
        provenance={
            "sensor_id": str(sensor.id),
            "threshold_source": limit_source,
            "reading_ids": [str(r.id) for r in valid_readings],
            "feature": feature.model_dump(mode="json"),
            "supporting_features": {
                "crest_factor": crest_factor_feature.value if crest_factor_feature else None,
                "kurtosis": kurtosis_feature.value if kurtosis_feature else None,
                "dominant_frequency_hz": dominant_freq_feature.value if dominant_freq_feature else None,
            },
        },
    )
    db.add(evidence)
    db.flush()

    exceedance = HUMSExceedance(
        organization_id=organization_id,
        sensor_id=sensor.id,
        asset_id=sensor.asset_id,
        component_id=sensor.component_id,
        parameter=feature.parameter,
        observed_value=feature.value,
        threshold_value=threshold,
        severity=severity,
        window_start=feature.window_start,
        window_end=feature.window_end,
        contributing_reading_ids=[str(r.id) for r in valid_readings],
        finding_id=finding.id,
    )
    db.add(exceedance)
    db.flush()

    _sync_exceedance_signal(
        db,
        organization_id=organization_id,
        sensor=sensor,
        exceedance=exceedance,
        finding=finding,
        supporting_features={
            "crest_factor": crest_factor_feature.value if crest_factor_feature else None,
            "kurtosis": kurtosis_feature.value if kurtosis_feature else None,
            "dominant_frequency_hz": dominant_freq_feature.value if dominant_freq_feature else None,
        },
    )

    audit_service.record_audit_event(
        db,
        organization_id=organization_id,
        user_id=user_id,
        action="hums_exceedance.detected",
        entity_type="HUMSExceedance",
        entity_id=exceedance.id,
        metadata={
            "asset_id": str(sensor.asset_id),
            "sensor_id": str(sensor.id),
            "severity": severity,
            "observed_value": feature.value,
            "threshold_value": threshold,
            "finding_id": str(finding.id),
        },
    )

    # Real-time downstream intelligence processing: diagnostics & prognostics on exceedance
    try:
        diagnostic_service.evaluate_and_persist_diagnostics(
            db,
            organization_id=organization_id,
            user_id=user_id,
            asset_id=sensor.asset_id,
            component_id=sensor.component_id,
            sensors=[sensor],
        )
        _evaluate_prognostics_for_sensors(
            db, organization_id=organization_id, sensors=[sensor]
        )
    except Exception:
        # Diagnostics/prognostics on exceedance are best-effort, but a failure must be visible.
        log.exception(
            "hums.downstream_evaluation_failed",
            organization_id=str(organization_id), sensor_id=str(sensor.id),
        )

    return HUMSExceedanceResponse.model_validate(exceedance)


def exceedance_signal_key(asset_id: uuid.UUID, sensor_id: uuid.UUID, window_end: datetime.datetime) -> str:
    """The ONE definition of an exceedance signal's dedup key.

    The window end is normalised to UTC: a datetime loaded from PostgreSQL carries the SESSION time
    zone (e.g. +05:30) while the same instant built in Python is +00:00, so `isoformat()` of the raw
    value gave two different keys for one exceedance and silently defeated de-duplication."""
    return f"hums_vibration_exceedance:{asset_id}:{sensor_id}:{window_end.astimezone(datetime.UTC).isoformat()}"


def _sync_exceedance_signal(
    db: Session,
    *,
    organization_id: uuid.UUID,
    sensor: HUMSSensor,
    exceedance: HUMSExceedance,
    finding: Finding,
    supporting_features: dict[str, float | None] | None = None,
) -> None:
    key = exceedance_signal_key(sensor.asset_id, sensor.id, exceedance.window_end)
    existing = db.execute(
        select(ProactiveSignalRecord).where(
            ProactiveSignalRecord.organization_id == organization_id,
            ProactiveSignalRecord.signal_key == key,
        )
    ).scalar_one_or_none()
    if existing:
        return

    evidence_ref = SignalEvidenceRef(
        source_type="HUMSExceedance",
        source_id=str(exceedance.id),
        label=f"Exceedance on sensor {sensor.sensor_code}",
        metric="vibration_rms",
        current_value=exceedance.observed_value,
        threshold_value=exceedance.threshold_value,
        details=f"Window {exceedance.window_start.isoformat()} -> {exceedance.window_end.isoformat()}",
    )

    record = ProactiveSignalRecord(
        organization_id=organization_id,
        signal_key=key,
        signal_type="HUMS_VIBRATION_EXCEEDANCE",
        severity=exceedance.severity,
        priority=exceedance.severity,
        status="OPEN",
        title=f"HUMS Vibration Exceedance — Sensor {sensor.sensor_code}",
        headline=(
            f"Vibration RMS {exceedance.observed_value} exceeded the "
            f"{exceedance.threshold_value} threshold on sensor {sensor.sensor_code}."
        ),
        explanation_json=[
            f"Sensor {sensor.sensor_code} recorded a vibration RMS of {exceedance.observed_value}, "
            f"above the {exceedance.severity.lower()} threshold of {exceedance.threshold_value}.",
            f"Finding {finding.id} was raised with supporting HUMS telemetry evidence.",
        ],
        asset_id=sensor.asset_id,
        component_id=sensor.component_id,
        detected_at=datetime.datetime.now(datetime.UTC),
        evidence_json=[evidence_ref.model_dump()],
        contributing_factors_json={
            "sensor_id": str(sensor.id),
            "finding_id": str(finding.id),
            "observed_value": exceedance.observed_value,
            "threshold_value": exceedance.threshold_value,
            **(supporting_features or {}),
        },
        recommended_actions_json=[
            {
                "action_type": "INSPECT_COMPONENT",
                "title": "Inspect Flagged Component",
                "description": f"Perform vibration diagnostic inspection on sensor {sensor.sensor_code}'s monitored component.",
                "target_url": f"/assets/{sensor.asset_id}",
                "requires_authorization": True,
            },
        ],
    )
    db.add(record)


def list_features(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    sensor_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    feature_type: str | None = None,
    limit: int = 200,
) -> list[HUMSFeature]:
    """Thin passthrough to app.services.hums.feature_service — keeps
    hums_service.py the single entry point the API layer calls into,
    consistent with how create_sensor/ingest_readings/etc. are exposed.
    """
    return feature_service.list_features(
        db,
        organization_id=organization_id,
        asset_id=asset_id,
        sensor_id=sensor_id,
        component_id=component_id,
        feature_type=feature_type,
        limit=limit,
    )


def get_sensor_spectrum(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID) -> dict:
    """On-demand FFT magnitude spectrum for the sensor's latest reading window."""
    sensor = _get_sensor(db, organization_id=organization_id, sensor_id=sensor_id)
    readings = _latest_readings(db, organization_id=organization_id, sensor_id=sensor.id)
    return feature_service.compute_spectrum(sensor, readings)


# --- H3: Baseline & Health Intelligence -----------------------------------


def _feature_health_to_response(sensor_id: uuid.UUID, result: FeatureHealthResult) -> HUMSFeatureHealthResponse:
    deviation_resp = None
    if result.deviation is not None:
        deviation_resp = HUMSDeviationResponse(
            sensor_id=sensor_id,
            feature_type=result.feature_type,
            current_value=result.deviation.current_value,
            baseline_value=result.deviation.baseline_value,
            lower_bound=result.deviation.lower_bound,
            upper_bound=result.deviation.upper_bound,
            absolute_deviation=result.deviation.absolute_deviation,
            percentage_deviation=result.deviation.percentage_deviation,
            standardized_deviation=result.deviation.standardized_deviation,
            state=result.deviation.state,
            baseline_quality=result.deviation.baseline_quality,
            confidence=result.deviation.confidence,
        )
    trend_resp = None
    if result.trend is not None:
        trend_resp = HUMSTrendResponse(
            sensor_id=sensor_id,
            feature_type=result.feature_type,
            direction=result.trend.direction,
            slope=result.trend.slope,
            rate_of_change=result.trend.rate_of_change,
            confidence=result.trend.confidence,
            sample_count=result.trend.sample_count,
            rolling_mean=result.trend.rolling_mean,
            rolling_std=result.trend.rolling_std,
        )
    return HUMSFeatureHealthResponse(
        sensor_id=sensor_id,
        feature_type=result.feature_type,
        state=result.state,
        consecutive_deviation_count=result.consecutive_deviation_count,
        explanation=result.explanation,
        confidence=result.confidence,
        deviation=deviation_resp,
        trend=trend_resp,
    )


def get_asset_baselines(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSBaselineResponse]:
    rows = baseline_service.list_asset_baselines(db, organization_id=organization_id, asset_id=asset_id)
    return [HUMSBaselineResponse.model_validate(r) for r in rows]


def get_asset_deviations(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSDeviationResponse]:
    sensors = list_sensors(db, organization_id=organization_id, asset_id=asset_id)
    results: list[HUMSDeviationResponse] = []
    for sensor in sensors:
        for ft in health_service.HEALTH_FEATURES_BY_MEASUREMENT_TYPE.get(
            sensor.measurement_type, [health_service.DEFAULT_HEALTH_FEATURE]
        ):
            fh = health_service.evaluate_feature_health(db, organization_id=organization_id, sensor=sensor, feature_type=ft)
            resp = _feature_health_to_response(sensor.id, fh)
            if resp.deviation:
                results.append(resp.deviation)
    return results


def get_asset_trends(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSTrendResponse]:
    sensors = list_sensors(db, organization_id=organization_id, asset_id=asset_id)
    results: list[HUMSTrendResponse] = []
    for sensor in sensors:
        for ft in health_service.HEALTH_FEATURES_BY_MEASUREMENT_TYPE.get(
            sensor.measurement_type, [health_service.DEFAULT_HEALTH_FEATURE]
        ):
            fh = health_service.evaluate_feature_health(db, organization_id=organization_id, sensor=sensor, feature_type=ft)
            resp = _feature_health_to_response(sensor.id, fh)
            if resp.trend:
                results.append(resp.trend)
    return results


def get_component_health_intelligence(
    db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> HUMSComponentHealthIntelligence:
    sensors = list(
        db.execute(
            select(HUMSSensor).where(
                HUMSSensor.organization_id == organization_id, HUMSSensor.component_id == component_id
            )
        )
        .scalars()
        .all()
    )
    aggregate, all_results = health_service.evaluate_component_health(db, organization_id=organization_id, sensors=sensors)

    if sensors:
        health_service.sync_health_signal(
            db, organization_id=organization_id, asset_id=sensors[0].asset_id, component_id=component_id,
            aggregate=aggregate, label=f"Component {component_id}",
        )
        # H4: diagnostic candidates are (re)evaluated alongside H3 health
        # intelligence -- same read-time, bounded-query precedent
        # sync_health_signal above already established.
        diagnostic_service.evaluate_and_persist_diagnostics(
            db, organization_id=organization_id, user_id=user_id, asset_id=sensors[0].asset_id,
            component_id=component_id, sensors=sensors,
        )
        _evaluate_prognostics_for_sensors(db, organization_id=organization_id, sensors=sensors)

    responses = [_feature_health_to_response(s.id, r) for s in sensors for r in health_service.evaluate_sensor_health(db, organization_id=organization_id, sensor=s)]
    primary_types = {c.feature_type for c in aggregate.primary_contributors}
    primary_responses = [r for r in responses if r.feature_type in primary_types and r.state == aggregate.state]

    return HUMSComponentHealthIntelligence(
        component_id=component_id, state=aggregate.state, confidence=aggregate.confidence,
        primary_contributors=primary_responses, all_contributors=responses,
    )


def get_asset_health_intelligence(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> HUMSAssetHealthIntelligence:
    """H3's explainable, baseline-driven health rollup. Kept separate from
    H1's `get_asset_health` (see HUMSAssetHealthIntelligence's docstring).
    """
    sensors = list_sensors(db, organization_id=organization_id, asset_id=asset_id)

    by_component: dict[uuid.UUID | None, list[HUMSSensor]] = {}
    for s in sensors:
        by_component.setdefault(s.component_id, []).append(s)

    components: list[HUMSComponentHealthIntelligence] = []
    all_feature_results: list[FeatureHealthResult] = []
    for component_id, group_sensors in by_component.items():
        aggregate, group_results = health_service.evaluate_component_health(
            db, organization_id=organization_id, sensors=group_sensors
        )
        all_feature_results.extend(group_results)

        label = f"Component {component_id}" if component_id else f"Asset {asset_id} (unassigned sensors)"
        health_service.sync_health_signal(
            db, organization_id=organization_id, asset_id=asset_id, component_id=component_id,
            aggregate=aggregate, label=label,
        )
        diagnostic_service.evaluate_and_persist_diagnostics(
            db, organization_id=organization_id, user_id=user_id, asset_id=asset_id,
            component_id=component_id, sensors=group_sensors,
        )
        _evaluate_prognostics_for_sensors(db, organization_id=organization_id, sensors=group_sensors)

        responses = [_feature_health_to_response(s.id, r) for s in group_sensors for r in health_service.evaluate_sensor_health(db, organization_id=organization_id, sensor=s)]
        primary_types = {c.feature_type for c in aggregate.primary_contributors}
        primary_responses = [r for r in responses if r.feature_type in primary_types and r.state == aggregate.state]
        components.append(
            HUMSComponentHealthIntelligence(
                component_id=component_id, state=aggregate.state, confidence=aggregate.confidence,
                primary_contributors=primary_responses, all_contributors=responses,
            )
        )

    from app.services.hums.health_engine import aggregate_health

    asset_aggregate = aggregate_health(all_feature_results)
    asset_primary_types = {c.feature_type for c in asset_aggregate.primary_contributors}
    all_responses = [r for comp in components for r in comp.all_contributors]
    asset_primary_responses = [r for r in all_responses if r.feature_type in asset_primary_types and r.state == asset_aggregate.state]

    return HUMSAssetHealthIntelligence(
        asset_id=asset_id,
        state=asset_aggregate.state,
        confidence=asset_aggregate.confidence,
        components=components,
        primary_contributors=asset_primary_responses,
        generated_at=datetime.datetime.now(datetime.UTC),
    )


# --- H4: Diagnostics & Fault Isolation --------------------------------------


def list_asset_diagnostics(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID):
    return diagnostic_service.list_asset_candidates(db, organization_id=organization_id, asset_id=asset_id)


def list_component_diagnostics(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID):
    return diagnostic_service.list_component_candidates(db, organization_id=organization_id, component_id=component_id)


def get_diagnostic(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID):
    return diagnostic_service.get_candidate(db, organization_id=organization_id, candidate_id=candidate_id)


def confirm_diagnostic(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID):
    return diagnostic_service.confirm_candidate(db, organization_id=organization_id, candidate_id=candidate_id, user_id=user_id)


def reject_diagnostic(db: Session, *, organization_id: uuid.UUID, candidate_id: uuid.UUID, user_id: uuid.UUID, reason: str):
    return diagnostic_service.reject_candidate(db, organization_id=organization_id, candidate_id=candidate_id, user_id=user_id, reason=reason)


# --- H5: Prognostics & Remaining Useful Life --------------------------------


def _evaluate_prognostics_for_sensors(db: Session, *, organization_id: uuid.UUID, sensors: list[HUMSSensor]) -> None:
    """Evaluated at the same read-time trigger point H3's health signals
    and H4's diagnostics already use (bounded, not an unbounded historical
    scan) — see docs/HUMS_RUL_ENGINE.md's async-boundary section.
    """
    for sensor in sensors:
        feature_types = health_service.HEALTH_FEATURES_BY_MEASUREMENT_TYPE.get(sensor.measurement_type)
        if not feature_types:
            continue
        for feature_type in feature_types:
            prognostic_service.evaluate_and_persist_prognostic(db, organization_id=organization_id, sensor=sensor, feature_type=feature_type)


def list_asset_prognostics(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSPrognosticRecord]:
    return list(
        db.execute(
            select(HUMSPrognosticRecord)
            .where(HUMSPrognosticRecord.organization_id == organization_id, HUMSPrognosticRecord.asset_id == asset_id, HUMSPrognosticRecord.is_current.is_(True))
            .order_by(HUMSPrognosticRecord.rul_estimate.asc().nulls_last())
        )
        .scalars()
        .all()
    )


def list_component_prognostics(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> list[HUMSPrognosticRecord]:
    return list(
        db.execute(
            select(HUMSPrognosticRecord)
            .where(HUMSPrognosticRecord.organization_id == organization_id, HUMSPrognosticRecord.component_id == component_id, HUMSPrognosticRecord.is_current.is_(True))
            .order_by(HUMSPrognosticRecord.rul_estimate.asc().nulls_last())
        )
        .scalars()
        .all()
    )


def get_prognostic(db: Session, *, organization_id: uuid.UUID, prognostic_id: uuid.UUID) -> HUMSPrognosticRecord:
    record = db.execute(
        select(HUMSPrognosticRecord).where(HUMSPrognosticRecord.id == prognostic_id, HUMSPrognosticRecord.organization_id == organization_id)
    ).scalar_one_or_none()
    if not record:
        raise NotFoundError("Prognostic record not found", code="hums_prognostic_not_found")
    return record


def list_asset_degradation_models(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSDegradationModel]:
    return list(
        db.execute(
            select(HUMSDegradationModel)
            .where(HUMSDegradationModel.organization_id == organization_id, HUMSDegradationModel.asset_id == asset_id, HUMSDegradationModel.is_current.is_(True))
        )
        .scalars()
        .all()
    )


def list_component_degradation_models(db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID) -> list[HUMSDegradationModel]:
    return list(
        db.execute(
            select(HUMSDegradationModel)
            .where(HUMSDegradationModel.organization_id == organization_id, HUMSDegradationModel.component_id == component_id, HUMSDegradationModel.is_current.is_(True))
        )
        .scalars()
        .all()
    )


__all__ = [
    "create_sensor",
    "list_sensors",
    "ingest_readings",
    "evaluate_sensor_health",
    "get_asset_health",
    "detect_and_record_exceedances",
    "list_features",
    "get_sensor_spectrum",
    "get_asset_baselines",
    "get_asset_deviations",
    "get_asset_trends",
    "get_component_health_intelligence",
    "get_asset_health_intelligence",
    "list_asset_diagnostics",
    "list_component_diagnostics",
    "get_diagnostic",
    "confirm_diagnostic",
    "reject_diagnostic",
    "list_asset_prognostics",
    "list_component_prognostics",
    "get_prognostic",
    "list_asset_degradation_models",
    "list_component_degradation_models",
]
