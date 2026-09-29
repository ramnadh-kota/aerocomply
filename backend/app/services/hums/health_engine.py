"""H3: Deviation, trend, change detection, and health-state rules — pure
functions/dataclasses over feature values and a BaselineStats. No DB access;
app.services.hums.health_service owns querying HUMSFeature/HUMSBaseline and
calling into this module.

Design note: these are deterministic rule tables with small, documented
constants (thresholds, sample-count minimums) — not statistical models and
not ML. See docs/HUMS_HEALTH_INTELLIGENCE.md for the full rule catalog and
the explicit statement that this is NOT fault diagnosis, RUL, or prognosis.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from app.services.hums.baseline_engine import BaselineStats, Confidence

DeviationState = Literal["NORMAL", "ELEVATED", "DEVIATED", "SEVERE", "INSUFFICIENT_DATA"]
TrendDirection = Literal["INCREASING", "DECREASING", "STABLE", "VOLATILE", "ACCELERATING", "INSUFFICIENT_DATA"]
HealthState = Literal["HEALTHY", "WATCH", "DEGRADED", "WARNING", "CRITICAL", "UNKNOWN", "INSUFFICIENT_DATA"]

MIN_SAMPLES_FOR_TREND = 5
# Coefficient-of-variation (std/|mean|) above this marks a trend VOLATILE
# rather than trusting a slope computed over noisy data.
VOLATILE_CV_THRESHOLD = 0.5
# A trend counts as ACCELERATING when the second half of the window's slope
# magnitude exceeds the first half's by this multiple, in the same direction.
ACCELERATION_RATIO_THRESHOLD = 1.5

_HEALTH_RANK: dict[HealthState, int] = {
    "INSUFFICIENT_DATA": 0,
    "UNKNOWN": 0,
    "HEALTHY": 1,
    "WATCH": 2,
    "DEGRADED": 3,
    "WARNING": 4,
    "CRITICAL": 5,
}


@dataclasses.dataclass(frozen=True)
class DeviationResult:
    current_value: float
    baseline_value: float  # mean
    lower_bound: float
    upper_bound: float
    absolute_deviation: float
    percentage_deviation: float | None
    standardized_deviation: float | None
    state: DeviationState
    baseline_quality: str
    confidence: Confidence


@dataclasses.dataclass(frozen=True)
class TrendResult:
    direction: TrendDirection
    slope: float | None
    rate_of_change: float | None
    confidence: Confidence
    sample_count: int
    window_start_seconds: float | None
    window_end_seconds: float | None
    rolling_mean: float | None
    rolling_std: float | None


@dataclasses.dataclass(frozen=True)
class FeatureHealthResult:
    feature_type: str
    state: HealthState
    deviation: DeviationResult | None
    trend: TrendResult | None
    consecutive_deviation_count: int
    explanation: list[str]
    confidence: Confidence


def compute_deviation(current_value: float, baseline: BaselineStats | None) -> DeviationResult:
    if baseline is None:
        return DeviationResult(
            current_value=current_value, baseline_value=0.0, lower_bound=0.0, upper_bound=0.0,
            absolute_deviation=0.0, percentage_deviation=None, standardized_deviation=None,
            state="INSUFFICIENT_DATA", baseline_quality="INSUFFICIENT_DATA", confidence="INSUFFICIENT_DATA",
        )

    absolute = current_value - baseline.mean
    pct = (absolute / baseline.mean) if baseline.mean != 0 else None
    standardized = (absolute / baseline.std_dev) if baseline.std_dev != 0 else None

    within_bounds = baseline.lower_bound <= current_value <= baseline.upper_bound
    if within_bounds:
        state: DeviationState = "NORMAL"
    elif standardized is None:
        # Zero-variance baseline but the value differs from it -- can't
        # express "how many std devs" so treat any deviation as SEVERE
        # rather than silently calling it NORMAL.
        state = "SEVERE"
    else:
        z = abs(standardized)
        if z < 2:
            state = "ELEVATED"
        elif z < 3:
            state = "DEVIATED"
        else:
            state = "SEVERE"

    return DeviationResult(
        current_value=current_value,
        baseline_value=baseline.mean,
        lower_bound=baseline.lower_bound,
        upper_bound=baseline.upper_bound,
        absolute_deviation=round(absolute, 6),
        percentage_deviation=round(pct, 6) if pct is not None else None,
        standardized_deviation=round(standardized, 6) if standardized is not None else None,
        state=state,
        baseline_quality=baseline.quality,
        confidence=baseline.confidence,
    )


def compute_trend(values: list[float], timestamps_seconds: list[float]) -> TrendResult:
    n = len(values)
    if n < MIN_SAMPLES_FOR_TREND:
        return TrendResult(
            direction="INSUFFICIENT_DATA", slope=None, rate_of_change=None, confidence="INSUFFICIENT_DATA",
            sample_count=n, window_start_seconds=None, window_end_seconds=None, rolling_mean=None, rolling_std=None,
        )

    import statistics as _stats

    mean = _stats.mean(values)
    std = _stats.pstdev(values)

    t_mean = sum(timestamps_seconds) / n
    denom = sum((t - t_mean) ** 2 for t in timestamps_seconds)
    slope = 0.0 if denom == 0 else sum((t - t_mean) * (v - mean) for t, v in zip(timestamps_seconds, values)) / denom
    duration = timestamps_seconds[-1] - timestamps_seconds[0]
    rate_of_change = (values[-1] - values[0]) / duration if duration > 0 else 0.0

    cv = (std / abs(mean)) if mean != 0 else float("inf")

    half = n // 2
    first_half_slope = _slope_of(values[:half], timestamps_seconds[:half]) if half >= 2 else None
    second_half_slope = _slope_of(values[half:], timestamps_seconds[half:]) if (n - half) >= 2 else None

    accelerating = False
    if first_half_slope is not None and second_half_slope is not None and first_half_slope != 0:
        same_direction = (first_half_slope > 0) == (second_half_slope > 0)
        if same_direction and abs(second_half_slope) >= abs(first_half_slope) * ACCELERATION_RATIO_THRESHOLD:
            accelerating = True

    if accelerating:
        direction: TrendDirection = "ACCELERATING"
    elif cv > VOLATILE_CV_THRESHOLD and abs(slope) * duration < std:
        # High relative noise AND the net movement over the window is
        # smaller than one standard deviation -- volatility, not a trend.
        direction = "VOLATILE"
    elif abs(slope) * duration < 0.5 * std if std > 0 else abs(slope) < 1e-9:
        direction = "STABLE"
    elif slope > 0:
        direction = "INCREASING"
    else:
        direction = "DECREASING"

    confidence: Confidence = "HIGH" if n >= 15 else ("MEDIUM" if n >= 8 else "LOW")

    return TrendResult(
        direction=direction,
        slope=round(slope, 8),
        rate_of_change=round(rate_of_change, 8),
        confidence=confidence,
        sample_count=n,
        window_start_seconds=timestamps_seconds[0],
        window_end_seconds=timestamps_seconds[-1],
        rolling_mean=round(mean, 6),
        rolling_std=round(std, 6),
    )


def _slope_of(values: list[float], timestamps: list[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    t_mean = sum(timestamps) / n
    v_mean = sum(values) / n
    denom = sum((t - t_mean) ** 2 for t in timestamps)
    if denom == 0:
        return 0.0
    return sum((t - t_mean) * (v - v_mean) for t, v in zip(timestamps, values)) / denom


def consecutive_deviation_count(values: list[float], baseline: BaselineStats | None) -> int:
    """Counts trailing (most-recent-first) values outside the baseline's
    [lower_bound, upper_bound] — distinguishes "3 consecutive abnormal
    observations" from "1 isolated abnormal observation" per the H3 spec.
    """
    if baseline is None or not values:
        return 0
    count = 0
    for v in reversed(values):
        if baseline.lower_bound <= v <= baseline.upper_bound:
            break
        count += 1
    return count


def determine_feature_health(
    *, feature_type: str, deviation: DeviationResult, trend: TrendResult, consecutive_count: int
) -> FeatureHealthResult:
    """Deterministic rule table turning (deviation state, trend direction,
    persistence) into a HealthState with an explanation. See
    docs/HUMS_HEALTH_INTELLIGENCE.md for the full rule catalog and worked
    examples matching the H3 spec's scenarios.
    """
    explanation: list[str] = []

    if deviation.state == "INSUFFICIENT_DATA":
        return FeatureHealthResult(
            feature_type=feature_type, state="INSUFFICIENT_DATA", deviation=deviation, trend=trend,
            consecutive_deviation_count=consecutive_count,
            explanation=[f"No baseline established for '{feature_type}' yet (insufficient history)."],
            confidence="INSUFFICIENT_DATA",
        )

    worsening_trend = trend.direction in ("INCREASING", "ACCELERATING") if deviation.absolute_deviation >= 0 else trend.direction in ("DECREASING", "ACCELERATING")

    if deviation.state == "SEVERE":
        if trend.direction == "ACCELERATING" or consecutive_count >= 5:
            state: HealthState = "CRITICAL"
            explanation.append(
                f"'{feature_type}' is severely outside its baseline range "
                f"({deviation.current_value} vs. [{deviation.lower_bound}, {deviation.upper_bound}])."
            )
            explanation.append(f"Deterioration is {trend.direction.lower()} and persistent ({consecutive_count} consecutive observations).")
        else:
            state = "WARNING"
            explanation.append(
                f"'{feature_type}' is severely outside its baseline range "
                f"({deviation.current_value} vs. [{deviation.lower_bound}, {deviation.upper_bound}])."
            )
    elif deviation.state == "DEVIATED":
        if worsening_trend or consecutive_count >= 5:
            state = "WARNING"
        else:
            state = "DEGRADED"
        explanation.append(
            f"'{feature_type}' deviates significantly from baseline "
            f"({deviation.percentage_deviation * 100:.1f}% from mean)." if deviation.percentage_deviation is not None
            else f"'{feature_type}' deviates significantly from baseline."
        )
        if consecutive_count >= 2:
            explanation.append(f"Elevated for {consecutive_count} consecutive observations.")
    elif deviation.state == "ELEVATED":
        if consecutive_count >= 3:
            state = "DEGRADED"
            explanation.append(f"'{feature_type}' has been mildly elevated for {consecutive_count} consecutive observations (persistent deviation).")
        else:
            state = "WATCH"
            explanation.append(f"'{feature_type}' is mildly outside its normal range (isolated/brief observation).")
    else:  # NORMAL
        state = "HEALTHY"
        explanation.append(f"'{feature_type}' is within its normal baseline range.")

    if trend.direction == "VOLATILE":
        explanation.append("Signal shows high variance relative to its historical baseline (noisy, not necessarily deteriorating).")

    return FeatureHealthResult(
        feature_type=feature_type,
        state=state,
        deviation=deviation,
        trend=trend,
        consecutive_deviation_count=consecutive_count,
        explanation=explanation,
        confidence=deviation.confidence,
    )


@dataclasses.dataclass(frozen=True)
class AggregateHealthResult:
    state: HealthState
    confidence: Confidence
    primary_contributors: list[FeatureHealthResult]
    all_contributors: list[FeatureHealthResult]


def aggregate_health(feature_results: list[FeatureHealthResult]) -> AggregateHealthResult:
    """Rolls a list of per-feature health results up to one state — the
    worst-ranked non-INSUFFICIENT_DATA state wins, never a numeric average
    that would obscure which feature is actually driving the verdict.
    """
    if not feature_results:
        return AggregateHealthResult(state="INSUFFICIENT_DATA", confidence="INSUFFICIENT_DATA", primary_contributors=[], all_contributors=[])

    ranked = sorted(feature_results, key=lambda f: _HEALTH_RANK[f.state], reverse=True)
    worst_rank = _HEALTH_RANK[ranked[0].state]

    if worst_rank == 0:
        return AggregateHealthResult(
            state="INSUFFICIENT_DATA", confidence="INSUFFICIENT_DATA", primary_contributors=[], all_contributors=feature_results
        )

    top_state: HealthState = ranked[0].state
    primary = [f for f in ranked if _HEALTH_RANK[f.state] == worst_rank]
    confidence = primary[0].confidence

    return AggregateHealthResult(state=top_state, confidence=confidence, primary_contributors=primary, all_contributors=ranked)


__all__ = [
    "DeviationResult",
    "TrendResult",
    "FeatureHealthResult",
    "AggregateHealthResult",
    "compute_deviation",
    "compute_trend",
    "consecutive_deviation_count",
    "determine_feature_health",
    "aggregate_health",
    "MIN_SAMPLES_FOR_TREND",
]
