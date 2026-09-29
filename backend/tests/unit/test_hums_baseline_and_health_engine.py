"""H3 Unit Tests: baseline statistics, deviation, trend, change detection,
and health-state rule table.
"""

from app.services.hums.baseline_engine import (
    GOOD_SAMPLES_THRESHOLD,
    LIMITED_SAMPLES_THRESHOLD,
    MIN_SAMPLES_FOR_BASELINE,
    compute_baseline_stats,
)
from app.services.hums.health_engine import (
    aggregate_health,
    compute_deviation,
    compute_trend,
    consecutive_deviation_count,
    determine_feature_health,
)

# --- Baseline calculation ---------------------------------------------------


def test_baseline_insufficient_samples():
    assert compute_baseline_stats([1.0, 2.0]) is None


def test_baseline_minimum_samples_boundary():
    values = [1.0] * MIN_SAMPLES_FOR_BASELINE
    stats = compute_baseline_stats(values)
    assert stats is not None
    assert stats.quality == "LIMITED"
    assert stats.confidence == "LOW"


def test_baseline_limited_quality():
    values = list(range(LIMITED_SAMPLES_THRESHOLD))
    stats = compute_baseline_stats([float(v) for v in values])
    assert stats.quality == "LIMITED"
    assert stats.confidence in ("MEDIUM",)


def test_baseline_valid_quality_and_confidence():
    values = [float(v % 10) for v in range(GOOD_SAMPLES_THRESHOLD)]
    stats = compute_baseline_stats(values)
    assert stats.quality == "VALID"
    assert stats.confidence == "HIGH"


def test_baseline_percentiles_and_bounds():
    values = [float(i) for i in range(1, 101)]  # 1..100
    stats = compute_baseline_stats(values)
    assert stats.percentile_50 == 50.0
    assert stats.lower_bound == stats.percentile_05
    assert stats.upper_bound == stats.percentile_95
    assert stats.minimum == 1.0
    assert stats.maximum == 100.0


def test_baseline_mean_and_stddev_known_values():
    stats = compute_baseline_stats([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    assert stats.mean == 5.0
    assert round(stats.std_dev, 2) == 2.0


# --- Deviation ---------------------------------------------------------------


def test_deviation_no_baseline_is_insufficient_data():
    dev = compute_deviation(5.0, None)
    assert dev.state == "INSUFFICIENT_DATA"


def test_deviation_within_bounds_is_normal():
    stats = compute_baseline_stats([1.0, 1.1, 0.9, 1.0, 1.2, 0.8, 1.0, 1.1] * 4)
    dev = compute_deviation(stats.mean, stats)
    assert dev.state == "NORMAL"


def test_deviation_severe_far_outside_bounds():
    stats = compute_baseline_stats([1.0 + 0.01 * (i % 3) for i in range(30)])
    dev = compute_deviation(stats.mean + 10 * stats.std_dev, stats)
    assert dev.state == "SEVERE"
    assert dev.standardized_deviation > 3


def test_deviation_percentage_zero_baseline_handled_safely():
    stats = compute_baseline_stats([0.0] * MIN_SAMPLES_FOR_BASELINE)
    dev = compute_deviation(5.0, stats)
    assert dev.percentage_deviation is None  # would divide by zero otherwise
    assert dev.state in ("SEVERE",)  # std_dev is 0 too, so standardized is also undefined -> SEVERE fallback


def test_deviation_absolute_and_standardized_known_values():
    stats = compute_baseline_stats([8.0, 9.0, 10.0, 11.0, 12.0] * 6)  # mean=10, std=sqrt(2)
    dev = compute_deviation(14.0, stats)
    assert dev.absolute_deviation == 4.0
    assert round(dev.standardized_deviation, 3) == round(4.0 / stats.std_dev, 3)


# --- Trend ---------------------------------------------------------------


def test_trend_insufficient_data():
    trend = compute_trend([1.0, 2.0], [0.0, 1.0])
    assert trend.direction == "INSUFFICIENT_DATA"


def test_trend_stable_flat_signal():
    values = [1.0] * 10
    ts = list(range(10))
    trend = compute_trend(values, [float(t) for t in ts])
    assert trend.direction == "STABLE"


def test_trend_increasing():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    ts = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    trend = compute_trend(values, ts)
    assert trend.direction == "INCREASING"
    assert trend.slope > 0


def test_trend_decreasing():
    values = [6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    ts = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    trend = compute_trend(values, ts)
    assert trend.direction == "DECREASING"
    assert trend.slope < 0


def test_trend_accelerating():
    # Slope in the second half is much steeper than the first half.
    values = [1.0, 1.1, 1.2, 1.3, 2.0, 4.0, 7.0, 11.0]
    ts = [float(i) for i in range(len(values))]
    trend = compute_trend(values, ts)
    assert trend.direction == "ACCELERATING"


def test_trend_volatile_high_noise_no_net_movement():
    values = [1.0, 5.0, 1.0, 5.0, 1.0, 5.0, 1.0, 5.0]
    ts = [float(i) for i in range(len(values))]
    trend = compute_trend(values, ts)
    assert trend.direction == "VOLATILE"


def test_trend_confidence_scales_with_sample_count():
    small = compute_trend([1.0, 2.0, 3.0, 4.0, 5.0], [0.0, 1.0, 2.0, 3.0, 4.0])
    large = compute_trend([float(i) for i in range(20)], [float(i) for i in range(20)])
    assert small.confidence == "LOW"
    assert large.confidence == "HIGH"


# --- Consecutive deviation / change detection --------------------------------


def test_consecutive_deviation_counts_trailing_only():
    stats = compute_baseline_stats([1.0] * 30)
    # stats has zero variance -> bounds collapse to [1.0, 1.0]; use a
    # baseline with real spread instead.
    stats = compute_baseline_stats([1.0 + 0.1 * (i % 3) for i in range(30)])
    values = [5.0, 5.0, 5.0, stats.mean, 5.0]  # isolated deviations broken by one normal value
    count = consecutive_deviation_count(values, stats)
    assert count == 1  # only the trailing value is deviated


def test_consecutive_deviation_all_deviated():
    stats = compute_baseline_stats([1.0 + 0.1 * (i % 3) for i in range(30)])
    values = [10.0, 10.0, 10.0]
    count = consecutive_deviation_count(values, stats)
    assert count == 3


def test_consecutive_deviation_none_baseline():
    assert consecutive_deviation_count([1.0, 2.0], None) == 0


# --- Health-state rule table ---------------------------------------------


def test_health_state_insufficient_data_when_no_baseline():
    dev = compute_deviation(5.0, None)
    trend = compute_trend([], [])
    result = determine_feature_health(feature_type="rms", deviation=dev, trend=trend, consecutive_count=0)
    assert result.state == "INSUFFICIENT_DATA"


def test_health_state_healthy_when_normal_and_stable():
    stats = compute_baseline_stats([1.0 + 0.05 * (i % 2) for i in range(30)])
    dev = compute_deviation(stats.mean, stats)
    trend = compute_trend([stats.mean] * 10, [float(i) for i in range(10)])
    result = determine_feature_health(feature_type="rms", deviation=dev, trend=trend, consecutive_count=0)
    assert result.state == "HEALTHY"


def test_health_state_watch_for_brief_mild_deviation():
    stats = compute_baseline_stats([1.0 + 0.1 * (i % 3) for i in range(30)])
    mild_outside = stats.upper_bound + 0.5 * stats.std_dev
    dev = compute_deviation(mild_outside, stats)
    trend = compute_trend([stats.mean] * 8 + [mild_outside], [float(i) for i in range(9)])
    result = determine_feature_health(feature_type="rms", deviation=dev, trend=trend, consecutive_count=1)
    assert result.state == "WATCH"


def test_health_state_degraded_for_persistent_mild_deviation():
    stats = compute_baseline_stats([1.0 + 0.1 * (i % 3) for i in range(30)])
    mild_outside = stats.upper_bound + 0.5 * stats.std_dev
    dev = compute_deviation(mild_outside, stats)
    trend = compute_trend([mild_outside] * 10, [float(i) for i in range(10)])
    result = determine_feature_health(feature_type="rms", deviation=dev, trend=trend, consecutive_count=4)
    assert result.state == "DEGRADED"


def test_health_state_critical_for_severe_and_accelerating():
    stats = compute_baseline_stats([1.0 + 0.1 * (i % 3) for i in range(30)])
    dev = compute_deviation(stats.mean + 10 * stats.std_dev, stats)
    values = [1.0, 1.1, 1.2, 1.3, 2.0, 4.0, 7.0, 20.0]
    trend = compute_trend(values, [float(i) for i in range(len(values))])
    result = determine_feature_health(feature_type="rms", deviation=dev, trend=trend, consecutive_count=6)
    assert result.state == "CRITICAL"
    assert result.explanation  # explainability requirement -- never a bare state


# --- Aggregation -----------------------------------------------------------


def test_aggregate_health_worst_state_wins():
    stats = compute_baseline_stats([1.0 + 0.1 * (i % 3) for i in range(30)])
    healthy_dev = compute_deviation(stats.mean, stats)
    critical_dev = compute_deviation(stats.mean + 10 * stats.std_dev, stats)
    trend = compute_trend([stats.mean] * 10, [float(i) for i in range(10)])

    healthy_result = determine_feature_health(feature_type="a", deviation=healthy_dev, trend=trend, consecutive_count=0)
    critical_result = determine_feature_health(feature_type="b", deviation=critical_dev, trend=trend, consecutive_count=6)

    aggregate = aggregate_health([healthy_result, critical_result])
    assert aggregate.state == critical_result.state
    assert any(c.feature_type == "b" for c in aggregate.primary_contributors)


def test_aggregate_health_empty_is_insufficient_data():
    aggregate = aggregate_health([])
    assert aggregate.state == "INSUFFICIENT_DATA"


def test_aggregate_health_all_insufficient_data():
    dev = compute_deviation(5.0, None)
    trend = compute_trend([], [])
    result = determine_feature_health(feature_type="a", deviation=dev, trend=trend, consecutive_count=0)
    aggregate = aggregate_health([result])
    assert aggregate.state == "INSUFFICIENT_DATA"
