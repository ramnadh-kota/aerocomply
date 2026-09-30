"""H5: Degradation trajectory fitting, threshold-crossing, and RUL
calculation — pure functions/dataclasses over (usage, value) pairs. No DB
access; app.services.hums.degradation_service owns querying HUMSFeature/
HUMSBaseline/usage data and persisting HUMSDegradationModel/
HUMSPrognosticRecord.

Deliberately explainable and deterministic: two model types only (LINEAR,
ROBUST_LINEAR — Theil-Sen). PIECEWISE_LINEAR and EXPONENTIAL are documented
extension points, not implemented (see docs/HUMS_RUL_ENGINE.md) — the H5
spec explicitly permits starting with the simplest models that explain the
observed degradation and warns against overfitting.

Every RUL result is an ESTIMATE, NOT A CERTIFIED LIFE LIMIT. Nothing here
computes a value with certification/regulatory standing.
"""

from __future__ import annotations

import dataclasses
import statistics
from typing import Literal

ModelType = Literal["LINEAR", "ROBUST_LINEAR", "INSUFFICIENT_DATA"]
TrajectoryState = Literal["STABLE", "DEGRADING", "ACCELERATING", "NON_MONOTONIC", "INSUFFICIENT_DATA", "UNKNOWN"]
PrognosticQuality = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA", "INVALID", "STALE"]
Confidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
ThresholdType = Literal["ENGINEERING_LIMIT", "MAINTENANCE_THRESHOLD", "WARNING_THRESHOLD", "CONFIGURED_PROGNOSTIC_THRESHOLD"]

MIN_SAMPLES_FOR_DEGRADATION = 6
# A trajectory covering less usage-span than this is too short to trust a
# slope extrapolated far beyond it. A heuristic confidence gate (not an engineering-derived minimum): it lowers the
# reported confidence, it never changes the fitted trajectory.
MIN_USAGE_SPAN_FOR_HIGH_CONFIDENCE = 10.0

# Normal-approximation multiplier used for the prediction range below.
# Labeled "approximate" throughout (never claimed as an exact Student-t
# confidence interval) since this codebase has no statistics dependency
# for an exact t-table — see docs/HUMS_RUL_ENGINE.md's uncertainty section.
_APPROX_90PCT_Z = 1.645


@dataclasses.dataclass(frozen=True)
class LinearFit:
    slope: float
    intercept: float
    fit_error: float  # RMSE of residuals
    r_squared: float
    residual_std: float
    sample_count: int
    usage_mean: float
    usage_sum_sq_dev: float  # sum((x - mean)^2), used for prediction-interval leverage term


def _predict(fit: LinearFit, x: float) -> float:
    return fit.intercept + fit.slope * x


def fit_linear(usage: list[float], values: list[float]) -> LinearFit | None:
    n = len(usage)
    if n < 2 or n != len(values):
        return None
    x_mean = sum(usage) / n
    y_mean = sum(values) / n
    sxx = sum((x - x_mean) ** 2 for x in usage)
    if sxx == 0:
        return None
    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(usage, values))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean

    residuals = [y - (intercept + slope * x) for x, y in zip(usage, values)]
    rmse = statistics.pstdev(residuals) if len(residuals) > 1 else abs(residuals[0])
    ss_res = sum(r**2 for r in residuals)
    ss_tot = sum((y - y_mean) ** 2 for y in values)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    return LinearFit(
        slope=slope, intercept=intercept, fit_error=round(rmse, 6), r_squared=round(max(0.0, r_squared), 4),
        residual_std=rmse, sample_count=n, usage_mean=x_mean, usage_sum_sq_dev=sxx,
    )


def fit_robust_linear(usage: list[float], values: list[float]) -> LinearFit | None:
    """Theil-Sen estimator: slope = median of all pairwise slopes. Robust
    to outliers that would otherwise skew an ordinary least-squares fit —
    used when `select_model` detects outlier residuals in the plain fit.
    """
    n = len(usage)
    if n < 2 or n != len(values):
        return None
    pairwise_slopes = [
        (values[j] - values[i]) / (usage[j] - usage[i])
        for i in range(n) for j in range(i + 1, n) if usage[j] != usage[i]
    ]
    if not pairwise_slopes:
        return None
    slope = statistics.median(pairwise_slopes)
    intercepts = [values[i] - slope * usage[i] for i in range(n)]
    intercept = statistics.median(intercepts)

    residuals = [y - (intercept + slope * x) for x, y in zip(usage, values)]
    rmse = statistics.pstdev(residuals) if len(residuals) > 1 else abs(residuals[0])
    y_mean = sum(values) / n
    ss_res = sum(r**2 for r in residuals)
    ss_tot = sum((y - y_mean) ** 2 for y in values)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    x_mean = sum(usage) / n
    sxx = sum((x - x_mean) ** 2 for x in usage)

    return LinearFit(
        slope=slope, intercept=intercept, fit_error=round(rmse, 6), r_squared=round(max(0.0, r_squared), 4),
        residual_std=rmse, sample_count=n, usage_mean=x_mean, usage_sum_sq_dev=sxx,
    )


@dataclasses.dataclass(frozen=True)
class ModelSelection:
    model_type: ModelType
    fit: LinearFit | None


def select_model(usage: list[float], values: list[float]) -> ModelSelection:
    """Prefers the simplest model (LINEAR) that explains the data; falls
    back to ROBUST_LINEAR only when the plain fit shows outlier-driven
    residuals (per spec: "prefer the simplest model that explains the
    observed degradation").
    """
    if len(usage) < MIN_SAMPLES_FOR_DEGRADATION:
        return ModelSelection("INSUFFICIENT_DATA", None)

    linear = fit_linear(usage, values)
    if linear is None:
        return ModelSelection("INSUFFICIENT_DATA", None)

    if linear.residual_std > 0:
        residuals = [y - _predict(linear, x) for x, y in zip(usage, values)]
        max_z = max(abs(r) / linear.residual_std for r in residuals)
        if max_z > 3.0:  # at least one residual is a clear outlier relative to the rest
            robust = fit_robust_linear(usage, values)
            if robust is not None:
                return ModelSelection("ROBUST_LINEAR", robust)

    return ModelSelection("LINEAR", linear)


def determine_trajectory_state(fit: LinearFit | None, values: list[float], degrading_direction: Literal[1, -1]) -> TrajectoryState:
    """degrading_direction: +1 if degradation means the feature INCREASES
    (e.g. vibration RMS), -1 if degradation means it DECREASES.
    """
    if fit is None or len(values) < MIN_SAMPLES_FOR_DEGRADATION:
        return "INSUFFICIENT_DATA"

    signed_slope = fit.slope * degrading_direction
    # STABLE: negligible net movement relative to noise over the observed span.
    span_effect = abs(fit.slope) * (max(1e-9, fit.usage_sum_sq_dev**0.5))
    if fit.residual_std > 0 and span_effect < 0.5 * fit.residual_std * (len(values) ** 0.5):
        return "STABLE"

    half = len(values) // 2
    if half >= 3:
        first_half_slope = fit_linear(list(range(half)), values[:half])
        second_half_slope = fit_linear(list(range(len(values) - half)), values[half:])
        if first_half_slope and second_half_slope:
            fh_signed = first_half_slope.slope * degrading_direction
            sh_signed = second_half_slope.slope * degrading_direction
            if fh_signed > 0 and sh_signed > fh_signed * 1.5:
                return "ACCELERATING"
            # Sign flip between halves with both slopes meaningfully nonzero -> non-monotonic.
            if fit.residual_std > 0:
                fh_significant = abs(first_half_slope.slope) > 0.1 * fit.residual_std
                sh_significant = abs(second_half_slope.slope) > 0.1 * fit.residual_std
                if fh_significant and sh_significant and (first_half_slope.slope > 0) != (second_half_slope.slope > 0):
                    return "NON_MONOTONIC"

    if signed_slope > 0:
        return "DEGRADING"
    return "STABLE"


@dataclasses.dataclass(frozen=True)
class RULEstimate:
    rul_point: float | None
    rul_lower: float | None
    rul_upper: float | None
    threshold_crossing_usage: float | None
    extrapolation_distance: float | None
    is_low_confidence_extrapolation: bool
    confidence: Confidence
    explanation: list[str]


def compute_threshold_crossing(fit: LinearFit, current_usage: float, threshold_value: float, degrading_direction: Literal[1, -1]) -> float | None:
    """Usage value at which the fitted trajectory reaches `threshold_value`,
    or None if the trajectory is moving away from (or parallel to) the
    threshold -- never fabricates a crossing point that the slope doesn't
    actually predict.
    """
    signed_slope = fit.slope * degrading_direction
    if signed_slope <= 0:
        return None
    predicted_threshold_signed = threshold_value * degrading_direction
    current_predicted_signed = _predict(fit, current_usage) * degrading_direction
    if predicted_threshold_signed <= current_predicted_signed:
        return current_usage  # already at/past threshold
    delta = (predicted_threshold_signed - current_predicted_signed) / signed_slope
    return current_usage + delta


def compute_rul(
    fit: LinearFit, current_usage: float, threshold_value: float, degrading_direction: Literal[1, -1], observed_usage_span: float,
) -> RULEstimate:
    crossing = compute_threshold_crossing(fit, current_usage, threshold_value, degrading_direction)
    if crossing is None:
        return RULEstimate(
            rul_point=None, rul_lower=None, rul_upper=None, threshold_crossing_usage=None,
            extrapolation_distance=None, is_low_confidence_extrapolation=False, confidence="LOW",
            explanation=["Trajectory is not moving toward the configured threshold -- no crossing predicted from current evidence."],
        )

    rul_point = max(0.0, crossing - current_usage)
    extrapolation_distance = max(0.0, crossing - (current_usage + observed_usage_span / 2))
    is_low_confidence = observed_usage_span > 0 and extrapolation_distance > observed_usage_span

    # Standard linear-regression prediction-interval formula (leverage term),
    # using a normal-approximation z-multiplier rather than an exact
    # Student-t critical value (this codebase has no stats dependency for
    # a t-table) -- labeled "approximate" everywhere it's surfaced.
    if fit.usage_sum_sq_dev > 0 and fit.sample_count > 2:
        leverage = 1.0 / fit.sample_count + ((crossing - fit.usage_mean) ** 2) / fit.usage_sum_sq_dev
        prediction_std = fit.residual_std * ((1 + leverage) ** 0.5)
    else:
        prediction_std = fit.residual_std

    margin_value = _APPROX_90PCT_Z * prediction_std
    signed_slope = fit.slope * degrading_direction
    margin_usage = (margin_value / abs(signed_slope)) if signed_slope != 0 else 0.0

    rul_lower = max(0.0, rul_point - margin_usage)
    rul_upper = rul_point + margin_usage

    if is_low_confidence:
        confidence: Confidence = "LOW"
    elif fit.r_squared >= 0.8 and observed_usage_span >= MIN_USAGE_SPAN_FOR_HIGH_CONFIDENCE:
        confidence = "HIGH"
    elif fit.r_squared >= 0.5:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    explanation = [
        f"Fitted trajectory crosses the configured threshold at usage {round(crossing, 2)}, "
        f"{round(rul_point, 2)} beyond the current observation.",
        f"Model fit quality (R^2): {fit.r_squared}.",
    ]
    if is_low_confidence:
        explanation.append(
            f"LOW_CONFIDENCE_EXTRAPOLATION: predicted crossing is {round(extrapolation_distance, 2)} beyond the observed "
            f"usage span of {round(observed_usage_span, 2)} -- the model is extrapolating further than it has evidence for."
        )

    return RULEstimate(
        rul_point=round(rul_point, 2), rul_lower=round(rul_lower, 2), rul_upper=round(rul_upper, 2),
        threshold_crossing_usage=round(crossing, 2), extrapolation_distance=round(extrapolation_distance, 2),
        is_low_confidence_extrapolation=is_low_confidence, confidence=confidence, explanation=explanation,
    )


def detect_model_drift(fit: LinearFit, recent_usage: list[float], recent_values: list[float]) -> bool:
    """MODEL_STALE signal: if the most recent observations deviate from
    what the existing fit predicts by more than 3 residual-std, the model
    no longer represents incoming data (H5 spec section 44).

    A near-perfect fit has residual_std near zero, which would otherwise
    make the 3-std threshold hypersensitive to ordinary floating-point
    noise (caught during H5 smoke testing: a numerically exact synthetic
    trajectory triggered false MODEL_STALE flags). `effective_std` floors
    the threshold at a small fraction of the predicted value's own
    magnitude so a real, meaningful deviation is still caught while
    floating-point-scale noise is not.
    """
    if not recent_usage:
        return False
    errors = [abs(y - _predict(fit, x)) for x, y in zip(recent_usage, recent_values)]
    predicted_magnitudes = [abs(_predict(fit, x)) for x in recent_usage]
    effective_std = max(fit.residual_std, 1e-6 * max([1.0, *predicted_magnitudes]))
    return any(e > 3 * effective_std for e in errors)


__all__ = [
    "LinearFit", "ModelSelection", "RULEstimate",
    "fit_linear", "fit_robust_linear", "select_model", "determine_trajectory_state",
    "compute_threshold_crossing", "compute_rul", "detect_model_drift",
    "MIN_SAMPLES_FOR_DEGRADATION", "MIN_USAGE_SPAN_FOR_HIGH_CONFIDENCE",
]
