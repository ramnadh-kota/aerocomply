"""Physically impossible sensor values are classified OUT_OF_RANGE (unit-aware) and never feed features."""
import datetime

import pytest

from app.services.hums.signal_processing import RawSample, build_signal_window, classify_reading_quality, physically_impossible

NOW = datetime.datetime(2026, 9, 30, 12, tzinfo=datetime.UTC)


@pytest.mark.parametrize("mtype,unit,value,impossible", [
    ("temperature", "degC", -273.16, True), ("temperature", "C", -300, True), ("temperature", "°C", -274, True),
    ("temperature", "degC", -273.15, False), ("temperature", "degC", -40, False), ("temperature", "K", -0.01, True),
    ("temperature", "K", 0.0, False), ("temperature", "degF", -460, True), ("temperature", "degF", -459.67, False),
    ("temperature", "furlongs", -10_000, False),            # unknown unit: never guessed
    ("rpm", "rpm", -1, True), ("rpm", "rpm", 0, False), ("rpm", "rpm", 6000, False),
    ("vibration", "mm/s", -50, False), ("voltage", "V", -12, False), ("current", "A", -300, False),
    ("torque", "percent", -5, False), ("pressure", "kPa", -30, False),
])
def test_physical_impossibility_is_narrow_and_unit_aware(mtype, unit, value, impossible):
    assert physically_impossible(mtype, unit, value) is impossible


def test_impossible_reading_is_out_of_range_even_if_declared_valid():
    q = classify_reading_quality(value=-300.0, recorded_at=NOW, declared_quality="VALID", newest_in_batch=NOW,
                                 measurement_type="temperature", unit="degC")
    assert q == "OUT_OF_RANGE"
    assert classify_reading_quality(value=20.0, recorded_at=NOW, declared_quality="VALID", newest_in_batch=NOW,
                                    measurement_type="temperature", unit="degC") == "VALID"


def test_window_excludes_impossible_readings_from_features():
    samples = [RawSample(id=str(i), recorded_at=NOW + datetime.timedelta(seconds=i), value=v, unit="degC",
                         data_quality="VALID") for i, v in enumerate([20.0, 21.0, -900.0, 22.0, 23.0, 24.0])]
    w = build_signal_window(sensor_id="s", asset_id="a", component_id=None, measurement_type="temperature",
                            unit="degC", source="T", samples=samples)
    assert w.sample_count == 5 and -900.0 not in w.values
    assert w.quality_summary.get("OUT_OF_RANGE") == 1 and w.overall_quality in ("GOOD", "DEGRADED")
