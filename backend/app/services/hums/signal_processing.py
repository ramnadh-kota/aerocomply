"""H2: Signal validation, preprocessing, and the SignalWindow abstraction.

Pure functions/dataclasses only — no DB session, no ORM. Callers
(feature_service.py) hand this module raw values/timestamps and get back a
validated, preprocessed window plus a data-quality verdict.
"""

from __future__ import annotations

import dataclasses
import datetime
import statistics
from typing import Literal

DataQuality = Literal["VALID", "SUSPECT", "MISSING", "OUT_OF_RANGE", "STALE", "DUPLICATE", "INVALID"]

# Generic catch-all sanity bounds (a reading beyond ±1e6 in any unit is garbage). They are NOT engineering limits:
# physically impossible values are rejected by `physically_impossible` (per measurement type / unit) and per-sensor
# operating limits are configured through the sensor thresholds API.
_SANITY_MIN = -1_000_000.0
_SANITY_MAX = 1_000_000.0

# A reading older than this relative to the window's newest reading is
# considered STALE rather than contributing to a "live" feature — prevents a
# long-idle sensor from silently blending ancient data into a fresh RMS.
STALE_AGE = datetime.timedelta(hours=6)


@dataclasses.dataclass(frozen=True)
class RawSample:
    """One input sample handed to the signal processor — mirrors the
    relevant subset of HUMSSensorReading without depending on the ORM.
    """

    id: str
    recorded_at: datetime.datetime
    value: float
    unit: str
    data_quality: DataQuality


@dataclasses.dataclass(frozen=True)
class SignalWindow:
    """A validated, preprocessed set of samples ready for feature extraction.

    `values`/`timestamps`/`sample_ids` are index-aligned and sorted
    ascending by timestamp. `estimated_sampling_rate_hz` is None when fewer
    than 2 samples remain after preprocessing (not enough to estimate a
    cadence).
    """

    sensor_id: str
    asset_id: str
    component_id: str | None
    measurement_type: str
    unit: str
    source: str
    values: list[float]
    timestamps: list[datetime.datetime]
    sample_ids: list[str]
    window_start: datetime.datetime
    window_end: datetime.datetime
    estimated_sampling_rate_hz: float | None
    quality_summary: dict[str, int]
    overall_quality: Literal["GOOD", "DEGRADED", "INSUFFICIENT_DATA", "INVALID"]

    @property
    def sample_count(self) -> int:
        return len(self.values)


_ABSOLUTE_ZERO = {"degc": -273.15, "c": -273.15, "celsius": -273.15, "k": 0.0, "kelvin": 0.0,
                  "degf": -459.67, "f": -459.67, "fahrenheit": -459.67}


def physically_impossible(measurement_type: str | None, unit: str | None, value: float) -> bool:
    """True for values no real sensor can report: a temperature below absolute zero (unit-aware) or a negative
    rotational speed. Deliberately narrow: quantities that may legitimately be negative (vibration samples, voltage,
    current, torque, gauge pressure) are never rejected here; per-sensor engineering limits are configured separately."""
    mtype, u = (measurement_type or "").lower(), (unit or "").strip().lower().replace("°", "deg")
    if mtype == "temperature":
        floor = _ABSOLUTE_ZERO.get(u)
        return floor is not None and value < floor
    if mtype == "rpm":
        return value < 0
    return False


def classify_reading_quality(
    *, value: float, recorded_at: datetime.datetime, declared_quality: DataQuality, newest_in_batch: datetime.datetime,
    measurement_type: str | None = None, unit: str | None = None,
) -> DataQuality:
    """Re-derives a reading's data-quality classification rather than
    trusting the declared value blindly — a caller could hand us "VALID"
    for an out-of-range or stale reading. The stricter of the two wins.
    """
    if declared_quality in ("MISSING", "INVALID", "DUPLICATE"):
        return declared_quality
    if value != value:  # NaN check without importing math for one use
        return "INVALID"
    if value < _SANITY_MIN or value > _SANITY_MAX or physically_impossible(measurement_type, unit, value):
        return "OUT_OF_RANGE"
    if newest_in_batch - recorded_at > STALE_AGE:
        return "STALE"
    return declared_quality if declared_quality == "SUSPECT" else "VALID"


def build_signal_window(
    *,
    sensor_id: str,
    asset_id: str,
    component_id: str | None,
    measurement_type: str,
    unit: str,
    source: str,
    samples: list[RawSample],
) -> SignalWindow:
    """Validates, deduplicates, sorts, and packages raw samples into a
    SignalWindow. Never raises on bad data — bad readings are excluded and
    reflected in `quality_summary`/`overall_quality` instead.
    """
    if not samples:
        return SignalWindow(
            sensor_id=sensor_id,
            asset_id=asset_id,
            component_id=component_id,
            measurement_type=measurement_type,
            unit=unit,
            source=source,
            values=[],
            timestamps=[],
            sample_ids=[],
            window_start=datetime.datetime.now(datetime.UTC),
            window_end=datetime.datetime.now(datetime.UTC),
            estimated_sampling_rate_hz=None,
            quality_summary={},
            overall_quality="INSUFFICIENT_DATA",
        )

    newest = max(s.recorded_at for s in samples)

    # Deduplicate on (recorded_at, value) — two identical (timestamp, value)
    # pairs are a duplicate transmission, not two distinct measurements.
    seen: set[tuple[datetime.datetime, float]] = set()
    deduped: list[RawSample] = []
    quality_summary: dict[str, int] = {}
    for s in sorted(samples, key=lambda x: x.recorded_at):
        key = (s.recorded_at, s.value)
        quality = classify_reading_quality(
            value=s.value, recorded_at=s.recorded_at, declared_quality=s.data_quality, newest_in_batch=newest,
            measurement_type=measurement_type, unit=s.unit or unit,
        )
        if key in seen:
            quality = "DUPLICATE"
        else:
            seen.add(key)
        quality_summary[quality] = quality_summary.get(quality, 0) + 1
        if quality == "VALID":
            deduped.append(s)

    if not deduped:
        overall: Literal["GOOD", "DEGRADED", "INSUFFICIENT_DATA", "INVALID"] = "INSUFFICIENT_DATA"
    elif quality_summary.get("VALID", 0) < len(samples):
        overall = "DEGRADED"
    else:
        overall = "GOOD"

    values = [s.value for s in deduped]
    timestamps = [s.recorded_at for s in deduped]
    sample_ids = [s.id for s in deduped]

    sampling_rate = None
    if len(timestamps) >= 2:
        deltas = [
            (timestamps[i + 1] - timestamps[i]).total_seconds()
            for i in range(len(timestamps) - 1)
            if (timestamps[i + 1] - timestamps[i]).total_seconds() > 0
        ]
        if deltas:
            median_dt = statistics.median(deltas)
            sampling_rate = round(1.0 / median_dt, 6) if median_dt > 0 else None

    return SignalWindow(
        sensor_id=sensor_id,
        asset_id=asset_id,
        component_id=component_id,
        measurement_type=measurement_type,
        unit=unit,
        source=source,
        values=values,
        timestamps=timestamps,
        sample_ids=sample_ids,
        window_start=min(timestamps) if timestamps else newest,
        window_end=max(timestamps) if timestamps else newest,
        estimated_sampling_rate_hz=sampling_rate,
        quality_summary=quality_summary,
        overall_quality=overall,
    )


__all__ = ["RawSample", "SignalWindow", "classify_reading_quality", "build_signal_window", "DataQuality"]
