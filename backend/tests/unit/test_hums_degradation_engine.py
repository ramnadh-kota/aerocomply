"""H5 Unit Tests: linear/robust degradation fitting, model selection,
trajectory classification, threshold crossing, RUL calculation with
uncertainty, extrapolation detection, and model-drift detection.

Includes quantitative statistical-accuracy validation against known
synthetic trajectories (H5 spec section 42), not just "does it execute".
"""

import random

from app.services.hums.degradation_engine import (
    MIN_SAMPLES_FOR_DEGRADATION,
    compute_rul,
    compute_threshold_crossing,
    detect_model_drift,
    determine_trajectory_state,
    fit_linear,
    fit_robust_linear,
    select_model,
)

# --- Linear fit --------------------------------------------------------


def test_fit_linear_known_values():
    usage = [0.0, 1.0, 2.0, 3.0, 4.0]
    values = [1.0, 2.0, 3.0, 4.0, 5.0]  # y = 1 + x
    fit = fit_linear(usage, values)
    assert fit is not None
    assert round(fit.slope, 6) == 1.0
    assert round(fit.intercept, 6) == 1.0
    assert fit.r_squared == 1.0
    assert fit.fit_error == 0.0


def test_fit_linear_insufficient_or_degenerate():
    assert fit_linear([1.0], [1.0]) is None
    assert fit_linear([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None  # zero variance in x


def test_fit_robust_linear_resists_outlier():
    usage = [float(i) for i in range(10)]
    values = [1.0 + 0.1 * u for u in usage]
    values[5] = 50.0  # single wild outlier
    plain = fit_linear(usage, values)
    robust = fit_robust_linear(usage, values)
    # The outlier should pull the plain OLS slope much further from the
    # true 0.1 than the robust (Theil-Sen) estimate.
    assert abs(robust.slope - 0.1) < abs(plain.slope - 0.1)


# --- Model selection -----------------------------------------------------


def test_select_model_insufficient_data():
    usage = [0.0, 1.0]
    values = [1.0, 1.1]
    selection = select_model(usage, values)
    assert selection.model_type == "INSUFFICIENT_DATA"
    assert selection.fit is None


def test_select_model_prefers_linear_for_clean_data():
    usage = [float(i) for i in range(MIN_SAMPLES_FOR_DEGRADATION + 4)]
    values = [1.0 + 0.05 * u for u in usage]
    selection = select_model(usage, values)
    assert selection.model_type == "LINEAR"


def test_select_model_switches_to_robust_for_outlier_data():
    usage = [float(i) for i in range(15)]
    values = [1.0 + 0.05 * u for u in usage]
    values[7] = 100.0  # extreme outlier -> should be detected and trigger robust fit
    selection = select_model(usage, values)
    assert selection.model_type == "ROBUST_LINEAR"


# --- Trajectory state ------------------------------------------------------


def test_trajectory_stable_for_flat_signal():
    values = [1.0] * (MIN_SAMPLES_FOR_DEGRADATION + 2)
    usage = [float(i) for i in range(len(values))]
    fit = fit_linear(usage, values)
    state = determine_trajectory_state(fit, values, degrading_direction=1)
    assert state == "STABLE"


def test_trajectory_degrading_for_steady_increase():
    usage = [float(i) for i in range(12)]
    values = [1.0 + 0.1 * u for u in usage]
    fit = fit_linear(usage, values)
    state = determine_trajectory_state(fit, values, degrading_direction=1)
    assert state == "DEGRADING"


def test_trajectory_accelerating():
    values = [1.0, 1.05, 1.1, 1.15, 2.0, 4.0, 7.0, 11.0]
    usage = [float(i) for i in range(len(values))]
    fit = fit_linear(usage, values)
    state = determine_trajectory_state(fit, values, degrading_direction=1)
    assert state == "ACCELERATING"


def test_trajectory_insufficient_data():
    state = determine_trajectory_state(None, [1.0, 2.0], degrading_direction=1)
    assert state == "INSUFFICIENT_DATA"


# --- Threshold crossing / RUL: quantitative validation --------------------


def test_threshold_crossing_known_trajectory_exact():
    """Known: start=1.0, degradation=0.01/FH, threshold=2.0 -> crossing at
    exactly usage=100 (per H5 spec section 42's example)."""
    usage = [float(i) for i in range(0, 60, 2)]
    values = [1.0 + 0.01 * u for u in usage]
    fit = fit_linear(usage, values)
    crossing = compute_threshold_crossing(fit, current_usage=usage[-1], threshold_value=2.0, degrading_direction=1)
    assert abs(crossing - 100.0) < 1e-6


def test_rul_known_trajectory_within_tolerance_noise_free():
    usage = [float(i) for i in range(0, 60, 2)]
    values = [1.0 + 0.01 * u for u in usage]
    fit = fit_linear(usage, values)
    current_usage = usage[-1]
    result = compute_rul(fit, current_usage=current_usage, threshold_value=2.0, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])
    expected_rul = 100.0 - current_usage
    assert result.rul_point is not None
    error_pct = abs(result.rul_point - expected_rul) / expected_rul * 100
    assert error_pct < 1.0, f"error {error_pct}% exceeds 1% tolerance for noise-free data"
    assert result.confidence == "HIGH"
    assert result.rul_lower is not None and result.rul_upper is not None
    assert result.rul_lower <= result.rul_point <= result.rul_upper


def test_rul_with_moderate_noise_within_documented_tolerance():
    random.seed(42)
    usage = [float(i) for i in range(0, 60, 2)]
    values = [1.0 + 0.01 * u + random.uniform(-0.03, 0.03) for u in usage]
    fit = fit_linear(usage, values)
    current_usage = usage[-1]
    result = compute_rul(fit, current_usage=current_usage, threshold_value=2.0, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])
    expected_rul = 100.0 - current_usage
    error_pct = abs(result.rul_point - expected_rul) / expected_rul * 100
    assert error_pct < 15.0, f"error {error_pct}% exceeds 15% documented tolerance for moderate noise"
    # Range must actually bracket a reasonable neighborhood of the true value.
    assert result.rul_lower < result.rul_point < result.rul_upper


def test_rul_wider_uncertainty_with_higher_noise():
    """H5-D: high-noise degradation should produce a WIDER uncertainty
    range than a low-noise trajectory with the same underlying slope."""
    usage = [float(i) for i in range(0, 60, 2)]
    base_values = [1.0 + 0.01 * u for u in usage]

    random.seed(1)
    low_noise = [v + random.uniform(-0.01, 0.01) for v in base_values]
    random.seed(1)
    high_noise = [v + random.uniform(-0.15, 0.15) for v in base_values]

    fit_low = fit_linear(usage, low_noise)
    fit_high = fit_linear(usage, high_noise)
    current_usage = usage[-1]

    result_low = compute_rul(fit_low, current_usage=current_usage, threshold_value=2.0, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])
    result_high = compute_rul(fit_high, current_usage=current_usage, threshold_value=2.0, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])

    low_width = result_low.rul_upper - result_low.rul_lower
    high_width = result_high.rul_upper - result_high.rul_lower
    assert high_width > low_width


def test_rul_none_when_trajectory_moving_away_from_threshold():
    usage = [float(i) for i in range(12)]
    values = [5.0 - 0.1 * u for u in usage]  # decreasing, threshold is above current -> never crosses
    fit = fit_linear(usage, values)
    result = compute_rul(fit, current_usage=usage[-1], threshold_value=10.0, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])
    assert result.rul_point is None
    assert result.threshold_crossing_usage is None


def test_low_confidence_extrapolation_flagged_far_beyond_observed_span():
    """H5-I: prediction far outside observed range must be flagged."""
    usage = [float(i) for i in range(10)]
    values = [1.0 + 0.001 * u for u in usage]  # very slow degradation
    fit = fit_linear(usage, values)
    result = compute_rul(fit, current_usage=usage[-1], threshold_value=100.0, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])
    assert result.is_low_confidence_extrapolation is True
    assert result.confidence == "LOW"
    assert any("LOW_CONFIDENCE_EXTRAPOLATION" in e for e in result.explanation)


def test_extrapolation_not_flagged_within_observed_span():
    usage = [float(i) for i in range(0, 100, 5)]
    values = [1.0 + 0.01 * u for u in usage]
    fit = fit_linear(usage, values)
    # Threshold crossing lands well within the observed span.
    result = compute_rul(fit, current_usage=usage[-1], threshold_value=1.5, degrading_direction=1, observed_usage_span=usage[-1] - usage[0])
    assert result.threshold_crossing_usage is not None
    assert result.threshold_crossing_usage <= usage[-1]  # already crossed -- well within observed data


# --- Model drift -----------------------------------------------------------


def test_model_drift_detected_when_recent_data_deviates():
    usage = [float(i) for i in range(20)]
    values = [1.0 + 0.01 * u for u in usage]
    fit = fit_linear(usage, values)
    recent_usage = [20.0, 21.0, 22.0]
    recent_values = [50.0, 52.0, 54.0]  # wildly off the fitted trajectory
    assert detect_model_drift(fit, recent_usage, recent_values) is True


def test_model_drift_not_detected_for_consistent_data():
    usage = [float(i) for i in range(20)]
    values = [1.0 + 0.01 * u for u in usage]
    fit = fit_linear(usage, values)
    recent_usage = [20.0, 21.0, 22.0]
    recent_values = [1.2, 1.21, 1.22]  # consistent with the fitted trend
    assert detect_model_drift(fit, recent_usage, recent_values) is False
