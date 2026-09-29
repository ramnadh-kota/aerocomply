"""H2: Feature extraction — time-domain, frequency-domain, and
domain-specific (per measurement_type) feature calculators.

Every function here is a pure computation over a list of floats (or a
SignalWindow) and returns a plain dict of {feature_type: FeatureResult}.
No DB access, no persistence — feature_service.py owns turning these into
HUMSFeature rows.

No numpy/scipy dependency: this codebase has none today, and a single FFT
of a few dozen-to-few-hundred samples per window does not warrant adding
one. The DFT below is a direct, textbook O(n^2) implementation — simple to
verify correct rather than fast; see test_hums_feature_engine.py's
synthetic-sine-wave test for the correctness check the spec requires.
"""

from __future__ import annotations

import cmath
import dataclasses
import math
import statistics
from typing import Literal

FeatureQuality = Literal["GOOD", "DEGRADED", "INSUFFICIENT_DATA", "INVALID"]

MIN_SAMPLES_FOR_STATS = 2
MIN_SAMPLES_FOR_SHAPE_STATS = 5  # kurtosis/skewness need enough points to be meaningful
MIN_SAMPLES_FOR_FFT = 8


@dataclasses.dataclass(frozen=True)
class FeatureResult:
    feature_type: str
    value: float | None
    unit: str
    quality: FeatureQuality
    calculation_method: str
    metadata: dict[str, float | int | str] = dataclasses.field(default_factory=dict)


def _std(values: list[float]) -> float:
    return statistics.pstdev(values)


def time_domain_statistics(values: list[float], unit: str) -> dict[str, FeatureResult]:
    """Basic statistics: min, max, mean, median, std, variance, range, p95."""
    if len(values) < MIN_SAMPLES_FOR_STATS:
        insufficient = FeatureResult(
            feature_type="", value=None, unit=unit, quality="INSUFFICIENT_DATA", calculation_method="n/a"
        )
        return {
            name: dataclasses.replace(insufficient, feature_type=name)
            for name in ("min", "max", "mean", "median", "std", "variance", "range", "p95")
        }

    vmin, vmax = min(values), max(values)
    mean = statistics.mean(values)
    median = statistics.median(values)
    std = _std(values)
    variance = statistics.pvariance(values)
    rng = vmax - vmin
    sorted_vals = sorted(values)
    p95_index = min(len(sorted_vals) - 1, max(0, math.ceil(0.95 * len(sorted_vals)) - 1))
    p95 = sorted_vals[p95_index]

    return {
        "min": FeatureResult("min", vmin, unit, "GOOD", "min()"),
        "max": FeatureResult("max", vmax, unit, "GOOD", "max()"),
        "mean": FeatureResult("mean", round(mean, 6), unit, "GOOD", "arithmetic_mean"),
        "median": FeatureResult("median", median, unit, "GOOD", "median"),
        "std": FeatureResult("std", round(std, 6), unit, "GOOD", "population_stdev"),
        "variance": FeatureResult("variance", round(variance, 6), unit, "GOOD", "population_variance"),
        "range": FeatureResult("range", rng, unit, "GOOD", "max_minus_min"),
        "p95": FeatureResult("p95", p95, unit, "GOOD", "nearest_rank_percentile"),
    }


def vibration_time_domain_features(values: list[float], unit: str) -> dict[str, FeatureResult]:
    """RMS, peak, peak-to-peak, crest factor, kurtosis, skewness.

    Kurtosis/skewness use the standard (Fisher, excess) definitions and
    require a non-zero standard deviation and MIN_SAMPLES_FOR_SHAPE_STATS
    samples — a constant or near-constant signal correctly reports
    INSUFFICIENT_DATA/INVALID for those two rather than dividing by zero.
    """
    if len(values) < MIN_SAMPLES_FOR_STATS:
        insufficient = FeatureResult(
            feature_type="", value=None, unit=unit, quality="INSUFFICIENT_DATA", calculation_method="n/a"
        )
        return {
            name: dataclasses.replace(insufficient, feature_type=name)
            for name in ("rms", "peak", "peak_to_peak", "crest_factor", "kurtosis", "skewness")
        }

    n = len(values)
    rms = math.sqrt(sum(v**2 for v in values) / n)
    peak = max(abs(v) for v in values)
    peak_to_peak = max(values) - min(values)

    results: dict[str, FeatureResult] = {
        "rms": FeatureResult("rms", round(rms, 6), unit, "GOOD", "sqrt(mean(x^2))"),
        "peak": FeatureResult("peak", round(peak, 6), unit, "GOOD", "max(abs(x))"),
        "peak_to_peak": FeatureResult("peak_to_peak", round(peak_to_peak, 6), unit, "GOOD", "max(x)-min(x)"),
    }

    if rms == 0:
        results["crest_factor"] = FeatureResult(
            "crest_factor", None, "ratio", "INVALID", "peak/rms", {"reason": "rms_is_zero"}
        )
    else:
        results["crest_factor"] = FeatureResult(
            "crest_factor", round(peak / rms, 6), "ratio", "GOOD", "peak/rms"
        )

    if n < MIN_SAMPLES_FOR_SHAPE_STATS:
        results["kurtosis"] = FeatureResult(
            "kurtosis", None, "unitless", "INSUFFICIENT_DATA", "fisher_excess_kurtosis",
            {"min_samples_required": MIN_SAMPLES_FOR_SHAPE_STATS},
        )
        results["skewness"] = FeatureResult(
            "skewness", None, "unitless", "INSUFFICIENT_DATA", "sample_skewness",
            {"min_samples_required": MIN_SAMPLES_FOR_SHAPE_STATS},
        )
    else:
        mean = statistics.mean(values)
        std = _std(values)
        if std == 0:
            results["kurtosis"] = FeatureResult(
                "kurtosis", None, "unitless", "INVALID", "fisher_excess_kurtosis", {"reason": "zero_variance"}
            )
            results["skewness"] = FeatureResult(
                "skewness", None, "unitless", "INVALID", "sample_skewness", {"reason": "zero_variance"}
            )
        else:
            m2 = sum((v - mean) ** 2 for v in values) / n
            m3 = sum((v - mean) ** 3 for v in values) / n
            m4 = sum((v - mean) ** 4 for v in values) / n
            skewness = m3 / (m2**1.5)
            kurtosis = m4 / (m2**2) - 3.0  # excess kurtosis (normal distribution == 0)
            results["kurtosis"] = FeatureResult("kurtosis", round(kurtosis, 6), "unitless", "GOOD", "fisher_excess_kurtosis")
            results["skewness"] = FeatureResult("skewness", round(skewness, 6), "unitless", "GOOD", "sample_skewness")

    return results


def _dft_magnitudes(values: list[float]) -> list[float]:
    """Direct O(n^2) discrete Fourier transform magnitude spectrum.

    Returns magnitudes for bins 0..n//2 (the non-redundant half of the
    spectrum for a real-valued input), normalized by n so magnitude is in
    the same units as the input signal.
    """
    n = len(values)
    half = n // 2 + 1
    magnitudes: list[float] = []
    for k in range(half):
        real = 0.0
        imag = 0.0
        for t, x in enumerate(values):
            angle = -2 * math.pi * k * t / n
            c = cmath.exp(complex(0, angle))
            real += x * c.real
            imag += x * c.imag
        magnitudes.append(math.hypot(real, imag) / n)
    return magnitudes


def frequency_domain_features(
    values: list[float], unit: str, sampling_rate_hz: float | None, band_edges_hz: tuple[float, float] = (0.0, float("inf"))
) -> dict[str, FeatureResult]:
    """Dominant frequency, total spectral energy, and in-band energy via a
    direct DFT. Skips DC (0 Hz) when identifying the dominant frequency,
    since a nonzero mean would otherwise always "win" trivially.
    """
    names = ("dominant_frequency", "spectral_energy", "band_energy")
    if len(values) < MIN_SAMPLES_FOR_FFT or not sampling_rate_hz or sampling_rate_hz <= 0:
        insufficient = FeatureResult(
            feature_type="", value=None, unit=unit, quality="INSUFFICIENT_DATA", calculation_method="n/a",
            metadata={"min_samples_required": MIN_SAMPLES_FOR_FFT, "requires_sampling_rate": True},
        )
        return {name: dataclasses.replace(insufficient, feature_type=name) for name in names}

    n = len(values)
    magnitudes = _dft_magnitudes(values)
    freq_resolution = sampling_rate_hz / n
    frequencies = [i * freq_resolution for i in range(len(magnitudes))]

    # Dominant frequency: largest-magnitude bin excluding DC (index 0).
    if len(magnitudes) > 1:
        dom_idx = max(range(1, len(magnitudes)), key=lambda i: magnitudes[i])
        dominant_freq = frequencies[dom_idx]
    else:
        dom_idx = 0
        dominant_freq = 0.0

    spectral_energy = sum(m**2 for m in magnitudes)
    lo, hi = band_edges_hz
    band_energy = sum(m**2 for f, m in zip(frequencies, magnitudes) if lo <= f <= hi)

    return {
        "dominant_frequency": FeatureResult(
            "dominant_frequency", round(dominant_freq, 4), "Hz", "GOOD", "dft_peak_magnitude_excl_dc",
            {"frequency_resolution_hz": round(freq_resolution, 4), "dominant_bin_magnitude": round(magnitudes[dom_idx], 6)},
        ),
        "spectral_energy": FeatureResult(
            "spectral_energy", round(spectral_energy, 6), f"{unit}^2", "GOOD", "sum_magnitude_squared"
        ),
        "band_energy": FeatureResult(
            "band_energy", round(band_energy, 6), f"{unit}^2", "GOOD", "sum_magnitude_squared_in_band",
            {"band_low_hz": lo, "band_high_hz": hi if hi != float("inf") else -1},
        ),
    }


def trend_features(values: list[float], timestamps_seconds: list[float], unit: str) -> dict[str, FeatureResult]:
    """Linear trend (least-squares slope) and rate-of-change, used for
    temperature/pressure/RPM/torque/voltage/current — measurement types
    where "is it drifting" matters more than shape statistics.
    """
    if len(values) < MIN_SAMPLES_FOR_STATS:
        insufficient = FeatureResult(
            feature_type="", value=None, unit=unit, quality="INSUFFICIENT_DATA", calculation_method="n/a"
        )
        return {name: dataclasses.replace(insufficient, feature_type=name) for name in ("trend", "rate_of_change")}

    n = len(values)
    t_mean = sum(timestamps_seconds) / n
    v_mean = sum(values) / n
    denom = sum((t - t_mean) ** 2 for t in timestamps_seconds)
    if denom == 0:
        slope = 0.0
    else:
        slope = sum((t - t_mean) * (v - v_mean) for t, v in zip(timestamps_seconds, values)) / denom

    duration = timestamps_seconds[-1] - timestamps_seconds[0]
    rate_of_change = (values[-1] - values[0]) / duration if duration > 0 else 0.0

    return {
        "trend": FeatureResult("trend", round(slope, 8), f"{unit}/s", "GOOD", "least_squares_slope"),
        "rate_of_change": FeatureResult(
            "rate_of_change", round(rate_of_change, 8), f"{unit}/s", "GOOD", "(last-first)/duration"
        ),
    }


def deviation_feature(values: list[float], baseline: float, unit: str) -> FeatureResult:
    """Deviation from a caller-supplied baseline (e.g. nominal pressure)."""
    if len(values) < MIN_SAMPLES_FOR_STATS:
        return FeatureResult("deviation", None, unit, "INSUFFICIENT_DATA", "n/a")
    mean = statistics.mean(values)
    return FeatureResult("deviation", round(mean - baseline, 6), unit, "GOOD", "mean_minus_baseline", {"baseline": baseline})


__all__ = [
    "FeatureResult",
    "time_domain_statistics",
    "vibration_time_domain_features",
    "frequency_domain_features",
    "trend_features",
    "deviation_feature",
    "MIN_SAMPLES_FOR_STATS",
    "MIN_SAMPLES_FOR_SHAPE_STATS",
    "MIN_SAMPLES_FOR_FFT",
]
