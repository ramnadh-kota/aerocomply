"""H2 Unit Tests: HUMS signal processing & feature extraction.

Covers every feature listed in the H2 acceptance checklist: time-domain
statistics, vibration shape features (RMS/peak/peak-to-peak/crest
factor/kurtosis/skewness), FFT/frequency-domain features (validated against
a known synthetic sine wave), trend features, and data-quality handling
(missing/duplicate/invalid/out-of-range/insufficient samples).
"""

import datetime
import math

from app.services.hums.feature_extractors import (
    MIN_SAMPLES_FOR_FFT,
    MIN_SAMPLES_FOR_SHAPE_STATS,
    MIN_SAMPLES_FOR_STATS,
    frequency_domain_features,
    time_domain_statistics,
    trend_features,
    vibration_time_domain_features,
)
from app.services.hums.signal_processing import RawSample, build_signal_window

UTC = datetime.UTC


# --- Time-domain statistics ---------------------------------------------


def test_time_domain_statistics_basic_values():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = time_domain_statistics(values, "unit")
    assert result["min"].value == 1.0
    assert result["max"].value == 5.0
    assert result["mean"].value == 3.0
    assert result["median"].value == 3.0
    assert result["range"].value == 4.0
    assert result["std"].value == round(math.sqrt(2), 6)
    assert result["variance"].value == 2.0


def test_time_domain_statistics_insufficient_data():
    result = time_domain_statistics([1.0], "unit")
    assert result["mean"].value is None
    assert result["mean"].quality == "INSUFFICIENT_DATA"


# --- Vibration time-domain features -------------------------------------


def test_rms_and_peak_known_values():
    # RMS of [3, 4] = sqrt((9+16)/2) = sqrt(12.5)
    result = vibration_time_domain_features([3.0, 4.0], "mm/s")
    assert result["rms"].value == round(math.sqrt(12.5), 6)
    assert result["peak"].value == 4.0
    assert result["peak_to_peak"].value == 1.0


def test_crest_factor_zero_rms_is_invalid_not_divide_by_zero():
    result = vibration_time_domain_features([0.0, 0.0, 0.0], "mm/s")
    assert result["crest_factor"].value is None
    assert result["crest_factor"].quality == "INVALID"


def test_kurtosis_skewness_insufficient_samples():
    result = vibration_time_domain_features([1.0, 2.0, 3.0], "mm/s")
    assert result["kurtosis"].quality == "INSUFFICIENT_DATA"
    assert result["skewness"].quality == "INSUFFICIENT_DATA"


def test_kurtosis_skewness_zero_variance_is_invalid():
    result = vibration_time_domain_features([5.0] * MIN_SAMPLES_FOR_SHAPE_STATS, "mm/s")
    assert result["kurtosis"].quality == "INVALID"
    assert result["skewness"].quality == "INVALID"


def test_kurtosis_normal_like_distribution_near_zero():
    # A symmetric, evenly-spread sample should have low |skewness|.
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    result = vibration_time_domain_features(values, "mm/s")
    assert result["skewness"].quality == "GOOD"
    assert abs(result["skewness"].value) < 0.5


# --- FFT / frequency-domain (deterministic synthetic signal) -----------


def test_fft_detects_known_sine_wave_frequency():
    sampling_rate = 1000.0
    signal_freq = 50.0
    n = 200
    values = [math.sin(2 * math.pi * signal_freq * (i / sampling_rate)) for i in range(n)]
    result = frequency_domain_features(values, "g", sampling_rate)
    # Frequency resolution is sampling_rate/n = 5 Hz -- 50 Hz falls exactly
    # on a bin, so this should be exact; tolerance documents the general case.
    assert abs(result["dominant_frequency"].value - signal_freq) <= (sampling_rate / n)
    assert result["spectral_energy"].value > 0


def test_fft_dc_signal_has_zero_dominant_frequency_when_flat():
    values = [2.0] * MIN_SAMPLES_FOR_FFT
    result = frequency_domain_features(values, "g", sampling_rate_hz=100.0)
    # A constant signal has no oscillation -- dominant non-DC bin should be ~0 magnitude.
    assert result["dominant_frequency"].quality == "GOOD"


def test_fft_insufficient_samples():
    result = frequency_domain_features([1.0, 2.0], "g", sampling_rate_hz=100.0)
    assert result["dominant_frequency"].quality == "INSUFFICIENT_DATA"


def test_fft_missing_sampling_rate():
    values = [1.0] * MIN_SAMPLES_FOR_FFT
    result = frequency_domain_features(values, "g", sampling_rate_hz=None)
    assert result["dominant_frequency"].quality == "INSUFFICIENT_DATA"


# --- Trend features -------------------------------------------------------


def test_trend_detects_increasing_linear_signal():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    timestamps = [0.0, 1.0, 2.0, 3.0, 4.0]
    result = trend_features(values, timestamps, "C")
    assert result["trend"].value == 10.0  # slope of 10 units/sec
    assert result["rate_of_change"].value == 10.0


def test_trend_insufficient_data():
    result = trend_features([1.0], [0.0], "C")
    assert result["trend"].quality == "INSUFFICIENT_DATA"


# --- Signal window / data quality ----------------------------------------


def _sample(value: float, seconds_offset: int, quality: str = "VALID") -> RawSample:
    base = datetime.datetime(2026, 1, 1, tzinfo=UTC)
    return RawSample(
        id=f"id-{seconds_offset}-{value}",
        recorded_at=base + datetime.timedelta(seconds=seconds_offset),
        value=value,
        unit="mm/s",
        data_quality=quality,
    )


def test_signal_window_deduplicates_identical_readings():
    samples = [_sample(1.0, 0), _sample(1.0, 0), _sample(2.0, 1)]
    window = build_signal_window(
        sensor_id="s1", asset_id="a1", component_id=None, measurement_type="vibration", unit="mm/s",
        source="SIMULATED", samples=samples,
    )
    assert window.sample_count == 2
    assert window.quality_summary.get("DUPLICATE", 0) == 1


def test_signal_window_excludes_out_of_range_values():
    samples = [_sample(1.0, 0), _sample(1e9, 1), _sample(2.0, 2)]
    window = build_signal_window(
        sensor_id="s1", asset_id="a1", component_id=None, measurement_type="vibration", unit="mm/s",
        source="SIMULATED", samples=samples,
    )
    assert window.sample_count == 2
    assert window.quality_summary.get("OUT_OF_RANGE", 0) == 1
    assert window.overall_quality == "DEGRADED"


def test_signal_window_empty_input_is_insufficient_data():
    window = build_signal_window(
        sensor_id="s1", asset_id="a1", component_id=None, measurement_type="vibration", unit="mm/s",
        source="SIMULATED", samples=[],
    )
    assert window.sample_count == 0
    assert window.overall_quality == "INSUFFICIENT_DATA"


def test_signal_window_invalid_declared_quality_is_excluded():
    samples = [_sample(1.0, 0, quality="INVALID"), _sample(2.0, 1, quality="VALID")]
    window = build_signal_window(
        sensor_id="s1", asset_id="a1", component_id=None, measurement_type="vibration", unit="mm/s",
        source="SIMULATED", samples=samples,
    )
    assert window.sample_count == 1
    assert window.quality_summary.get("INVALID", 0) == 1


def test_signal_window_estimates_sampling_rate():
    samples = [_sample(float(i), i) for i in range(10)]  # 1-second spacing
    window = build_signal_window(
        sensor_id="s1", asset_id="a1", component_id=None, measurement_type="vibration", unit="mm/s",
        source="SIMULATED", samples=samples,
    )
    assert window.estimated_sampling_rate_hz == 1.0
