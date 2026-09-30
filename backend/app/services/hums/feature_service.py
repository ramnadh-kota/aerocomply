"""H2: Orchestrates signal_processing + feature_extractors into persisted
HUMSFeature rows.

This is the only place in app/services/hums/ that touches the DB. It has no
knowledge of Finding/Evidence/ProactiveSignalRecord — hums_service.py reads
back the persisted features (or the return value of process_window) and
decides what, if anything, becomes an exceedance.

Asynchronous processing note (H2 spec section 20): this codebase has no
background-job infrastructure (no Celery/RQ/cron) anywhere — see
app/services/evidence_reconciliation_service.py's module docstring for the
same observation and the same deliberate decision not to introduce one for
a single feature. process_window() is therefore called synchronously from
hums_service.ingest path, but is a clean, self-contained function boundary
(readings in, features out, no request/response coupling) that could be
moved behind a queue consumer later without changing its signature.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hums import HUMSFeature, HUMSSensor, HUMSSensorReading
from app.services.hums.feature_extractors import (
    FeatureResult,
    deviation_feature,
    frequency_domain_features,
    time_domain_statistics,
    trend_features,
    vibration_time_domain_features,
)
from app.services.hums.signal_processing import RawSample, SignalWindow, build_signal_window

# Which feature set applies to which sensor.measurement_type. Extension
# point for H2 spec section 15: add a measurement_type here (and, if it
# needs a bespoke calculation, a branch in _compute_features) rather than
# hard-coding a new physical quantity into hums_service.py.
_TREND_MEASUREMENT_TYPES = {"temperature", "pressure", "rpm", "torque", "voltage", "current"}
_VIBRATION_MEASUREMENT_TYPES = {"vibration"}

PROCESSOR_VERSION = "h2.1"


def _to_window(sensor: HUMSSensor, readings: list[HUMSSensorReading]) -> SignalWindow:
    samples = [
        RawSample(
            id=str(r.id),
            recorded_at=r.recorded_at,
            value=r.value,
            unit=r.unit,
            data_quality=r.data_quality,  # type: ignore[arg-type]
        )
        for r in readings
    ]
    return build_signal_window(
        sensor_id=str(sensor.id),
        asset_id=str(sensor.asset_id),
        component_id=str(sensor.component_id) if sensor.component_id else None,
        measurement_type=sensor.measurement_type,
        unit=readings[0].unit if readings else sensor.unit,
        source=sensor.source,
        samples=samples,
    )


def _compute_features(window: SignalWindow) -> dict[str, FeatureResult]:
    features: dict[str, FeatureResult] = {}
    features.update(time_domain_statistics(window.values, window.unit))

    if window.measurement_type in _VIBRATION_MEASUREMENT_TYPES:
        features.update(vibration_time_domain_features(window.values, window.unit))
        features.update(
            frequency_domain_features(window.values, window.unit, window.estimated_sampling_rate_hz)
        )
    elif window.measurement_type in _TREND_MEASUREMENT_TYPES:
        t0 = window.timestamps[0] if window.timestamps else None
        ts_seconds = [(t - t0).total_seconds() for t in window.timestamps] if t0 else []
        features.update(trend_features(window.values, ts_seconds, window.unit))
        if window.measurement_type == "pressure" and window.values:
            # "deviation" here is the drift of the window from its OWN first reading. It is a relative trend
            # indicator, not a comparison against a nominal/OEM operating value (no such value is assumed).
            features["deviation"] = deviation_feature(window.values, baseline=window.values[0], unit=window.unit)

    return features


def process_window(
    db: Session, *, sensor: HUMSSensor, readings: list[HUMSSensorReading]
) -> list[HUMSFeature]:
    """Validates + preprocesses `readings` into a SignalWindow, extracts the
    feature set appropriate to `sensor.measurement_type`, and persists each
    as a traceable HUMSFeature row. Returns the persisted rows (flushed,
    not committed — caller controls the transaction, matching
    hums_service.py's existing convention).
    """
    window = _to_window(sensor, readings)
    computed = _compute_features(window)

    persisted: list[HUMSFeature] = []
    for feature_type, result in computed.items():
        # A per-feature INSUFFICIENT_DATA/INVALID verdict always wins (e.g.
        # kurtosis on a near-constant signal); otherwise a DEGRADED window
        # (some readings excluded) downgrades an otherwise-GOOD feature.
        if result.quality in ("INSUFFICIENT_DATA", "INVALID"):
            quality = result.quality
        elif window.overall_quality == "DEGRADED":
            quality = "DEGRADED"
        else:
            quality = result.quality

        row = HUMSFeature(
            organization_id=sensor.organization_id,
            sensor_id=sensor.id,
            asset_id=sensor.asset_id,
            component_id=sensor.component_id,
            measurement_type=sensor.measurement_type,
            feature_type=feature_type,
            value=result.value if result.value is not None else 0.0,
            unit=result.unit,
            window_start=window.window_start,
            window_end=window.window_end,
            sample_count=window.sample_count,
            quality=quality,
            calculation_method=result.calculation_method,
            processor_version=PROCESSOR_VERSION,
            source_reading_ids=window.sample_ids,
            feature_metadata={**result.metadata, "quality_summary": window.quality_summary},
        )
        db.add(row)
        persisted.append(row)

    db.flush()
    return persisted


def get_feature(persisted: list[HUMSFeature], feature_type: str) -> HUMSFeature | None:
    return next((f for f in persisted if f.feature_type == feature_type), None)


def compute_spectrum(sensor: HUMSSensor, readings: list[HUMSSensorReading]) -> dict:
    """On-demand DFT magnitude spectrum for the frontend frequency view — not
    persisted (see HUMSSpectrumResponse's docstring for why).
    """
    from app.services.hums.feature_extractors import MIN_SAMPLES_FOR_FFT, _dft_magnitudes

    window = _to_window(sensor, readings)
    if window.sample_count < MIN_SAMPLES_FOR_FFT or not window.estimated_sampling_rate_hz:
        return {
            "sensor_id": str(sensor.id),
            "unit": window.unit,
            "sampling_rate_hz": window.estimated_sampling_rate_hz,
            "frequency_resolution_hz": None,
            "frequencies_hz": [],
            "magnitudes": [],
            "dominant_frequency_hz": None,
            "sample_count": window.sample_count,
            "window_start": window.window_start if window.values else None,
            "window_end": window.window_end if window.values else None,
            "quality": "INSUFFICIENT_DATA",
        }

    magnitudes = _dft_magnitudes(window.values)
    n = window.sample_count
    freq_resolution = window.estimated_sampling_rate_hz / n
    frequencies = [round(i * freq_resolution, 4) for i in range(len(magnitudes))]
    dom_idx = max(range(1, len(magnitudes)), key=lambda i: magnitudes[i]) if len(magnitudes) > 1 else 0

    return {
        "sensor_id": str(sensor.id),
        "unit": window.unit,
        "sampling_rate_hz": window.estimated_sampling_rate_hz,
        "frequency_resolution_hz": round(freq_resolution, 4),
        "frequencies_hz": frequencies,
        "magnitudes": [round(m, 6) for m in magnitudes],
        "dominant_frequency_hz": frequencies[dom_idx] if magnitudes else None,
        "sample_count": n,
        "window_start": window.window_start,
        "window_end": window.window_end,
        "quality": window.overall_quality,
    }


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
    query = select(HUMSFeature).where(HUMSFeature.organization_id == organization_id)
    if asset_id:
        query = query.where(HUMSFeature.asset_id == asset_id)
    if sensor_id:
        query = query.where(HUMSFeature.sensor_id == sensor_id)
    if component_id:
        query = query.where(HUMSFeature.component_id == component_id)
    if feature_type:
        query = query.where(HUMSFeature.feature_type == feature_type)
    query = query.order_by(HUMSFeature.window_end.desc()).limit(min(limit, 1000))
    return list(db.execute(query).scalars().all())


__all__ = ["process_window", "get_feature", "list_features", "PROCESSOR_VERSION"]
