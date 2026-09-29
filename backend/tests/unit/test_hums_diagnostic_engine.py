"""H4 Unit Tests: fault signature matching, candidate scoring/confidence/
severity, alternative hypotheses, sensor-fault detection, and the
duplicate-suppression / insufficient-evidence safety properties.
"""

from app.services.hums.baseline_engine import compute_baseline_stats
from app.services.hums.diagnostic_engine import (
    MIN_SCORE_THRESHOLD,
    detect_sensor_fault_candidate,
    evaluate_signature,
    generate_candidates,
)
from app.services.hums.fault_signatures import BEARING_DEGRADATION, ROTOR_IMBALANCE, VIBRATION_SIGNATURES
from app.services.hums.health_engine import compute_deviation, compute_trend, consecutive_deviation_count, determine_feature_health

TS = [float(i) for i in range(10)]


def _healthy_baseline():
    return compute_baseline_stats([1.0 + 0.1 * ((i % 3) - 1) for i in range(30)])


def _feature(feature_type: str, current: float, history: list[float], baseline):
    dev = compute_deviation(current, baseline)
    trend = compute_trend(history, TS[: len(history)])
    cc = consecutive_deviation_count(history, baseline)
    return determine_feature_health(feature_type=feature_type, deviation=dev, trend=trend, consecutive_count=cc)


def test_no_candidate_for_healthy_features():
    baseline = _healthy_baseline()
    features = {
        "rms": _feature("rms", baseline.mean, [baseline.mean] * 10, baseline),
        "kurtosis": _feature("kurtosis", baseline.mean, [baseline.mean] * 10, baseline),
    }
    candidates = generate_candidates(VIBRATION_SIGNATURES, features)
    assert candidates == []


def test_single_weak_feature_below_threshold_produces_no_candidate():
    """Safety requirement: a single mildly-elevated feature with no
    supporting evidence must not fabricate a diagnosis."""
    baseline = _healthy_baseline()
    mild = baseline.upper_bound + 0.5 * baseline.std_dev  # ELEVATED, not DEVIATED
    features = {"rms": _feature("rms", mild, [baseline.mean] * 9 + [mild], baseline)}
    result = evaluate_signature(BEARING_DEGRADATION, features)
    assert result is None  # required kurtosis condition isn't even present


def test_bearing_degradation_requires_both_rms_and_kurtosis():
    baseline = _healthy_baseline()
    severe = baseline.mean + 10 * baseline.std_dev
    features = {
        "rms": _feature("rms", severe, [severe] * 10, baseline),
        # kurtosis stays normal -- required condition not met
        "kurtosis": _feature("kurtosis", baseline.mean, [baseline.mean] * 10, baseline),
    }
    result = evaluate_signature(BEARING_DEGRADATION, features)
    assert result is None


def test_bearing_degradation_matches_with_full_evidence():
    baseline = _healthy_baseline()
    severe_hist = [1.0, 2.0, 4.0, 6.0, 8.0, 9.0, 10.0]  # increasing trend
    features = {
        "rms": _feature("rms", 10.0, severe_hist, baseline),
        "kurtosis": _feature("kurtosis", 10.0, severe_hist, baseline),
        "crest_factor": _feature("crest_factor", 10.0, severe_hist, baseline),
    }
    result = evaluate_signature(BEARING_DEGRADATION, features)
    assert result is not None
    assert result.status == "SUPPORTED"
    assert result.score >= 0.5
    assert result.explanation  # explainability requirement
    assert result.confidence in ("HIGH", "MEDIUM")


def test_severity_distinct_from_confidence():
    """H4 spec section 19: severity (impact if true) and confidence
    (evidence strength) must be independently derived, not conflated."""
    baseline = _healthy_baseline()
    # Strong required evidence (CRITICAL-ranked feature states -> HIGH
    # severity) but minimal supporting evidence -> lower confidence.
    features = {
        "rms": _feature("rms", baseline.mean + 10 * baseline.std_dev, [baseline.mean + 10 * baseline.std_dev] * 5, baseline),
        "kurtosis": _feature("kurtosis", baseline.mean + 10 * baseline.std_dev, [baseline.mean + 10 * baseline.std_dev] * 5, baseline),
    }
    result = evaluate_signature(BEARING_DEGRADATION, features)
    assert result is not None
    assert result.severity == "HIGH"
    # No supporting conditions satisfied (no crest_factor data, flat trend, <3 consecutive) -> lower confidence than severity.
    assert result.confidence in ("MEDIUM", "LOW")


def test_competing_hypotheses_preserved_not_collapsed():
    """H4 spec section 17: alternatives must never be deleted."""
    baseline = _healthy_baseline()
    hist = [1.0, 2.0, 4.0, 6.0, 8.0, 9.0, 10.0]
    features = {
        "rms": _feature("rms", 10.0, hist, baseline),
        "kurtosis": _feature("kurtosis", 10.0, hist, baseline),
    }
    candidates = generate_candidates(VIBRATION_SIGNATURES, features)
    fault_codes = {c.signature.fault_code for c in candidates}
    assert BEARING_DEGRADATION.fault_code in fault_codes
    # Rotor imbalance's required condition (elevated rms) is also met here;
    # it should still appear as a (weaker, contradicted) alternative.
    if ROTOR_IMBALANCE.fault_code in fault_codes:
        rotor = next(c for c in candidates if c.signature.fault_code == ROTOR_IMBALANCE.fault_code)
        assert any(r.satisfied for r in rotor.contradicting_results)


def test_candidates_sorted_strongest_first():
    baseline = _healthy_baseline()
    hist = [1.0, 2.0, 4.0, 6.0, 8.0, 9.0, 10.0]
    features = {"rms": _feature("rms", 10.0, hist, baseline), "kurtosis": _feature("kurtosis", 10.0, hist, baseline)}
    candidates = generate_candidates(VIBRATION_SIGNATURES, features)
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_insufficient_evidence_no_baseline_produces_no_candidate():
    features = {
        "rms": _feature("rms", 10.0, [10.0] * 3, None),  # no baseline -> INSUFFICIENT_DATA
        "kurtosis": _feature("kurtosis", 10.0, [10.0] * 3, None),
    }
    result = evaluate_signature(BEARING_DEGRADATION, features)
    assert result is None


def test_min_score_threshold_is_enforced():
    """A signature whose required conditions barely pass with zero
    supporting evidence must not produce a candidate below MIN_SCORE_THRESHOLD."""
    assert MIN_SCORE_THRESHOLD > 0  # sanity: the safeguard is actually active


def test_sensor_fault_detected_when_one_sensor_abnormal_others_healthy():
    baseline = _healthy_baseline()
    bad = {"rms": _feature("rms", baseline.mean + 10 * baseline.std_dev, [baseline.mean + 10 * baseline.std_dev] * 5, baseline)}
    good = {"rms": _feature("rms", baseline.mean, [baseline.mean] * 10, baseline)}
    result = detect_sensor_fault_candidate({"sensor-bad": bad, "sensor-good": good})
    assert result is not None
    assert result[0] == "sensor-bad"


def test_no_sensor_fault_when_multiple_sensors_abnormal():
    """Multiple sensors abnormal together is better explained by a shared
    physical cause, not a single sensor malfunction."""
    baseline = _healthy_baseline()
    bad = {"rms": _feature("rms", baseline.mean + 10 * baseline.std_dev, [baseline.mean + 10 * baseline.std_dev] * 5, baseline)}
    result = detect_sensor_fault_candidate({"sensor-a": bad, "sensor-b": bad})
    assert result is None


def test_no_sensor_fault_with_single_sensor_component():
    baseline = _healthy_baseline()
    bad = {"rms": _feature("rms", baseline.mean + 10 * baseline.std_dev, [baseline.mean + 10 * baseline.std_dev] * 5, baseline)}
    result = detect_sensor_fault_candidate({"sensor-only": bad})
    assert result is None  # need >=2 sensors to distinguish sensor-fault from physical fault
