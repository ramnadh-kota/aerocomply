"""H4: Diagnostic candidate generation — pure functions over H3
FeatureHealthResult data and the fault_signatures registry. No DB access;
app.services.hums.diagnostic_service owns persistence.

Scoring is a deterministic, explainable formula (never a black-box number):

    score = clamp(0, 1,
        REQUIRED_BASE
        + SUPPORTING_WEIGHT * (satisfied_supporting_weight / total_supporting_weight)
        - CONTRADICTING_WEIGHT * (satisfied_contradicting_weight / max(1, total_contradicting_weight))
    )

Every contributing condition (required/supporting/contradicting, satisfied
or not) is retained in the returned DiagnosticEvaluation so a caller can
show exactly which evidence drove the score — see
docs/HUMS_DIAGNOSTICS.md's "no black box" section.
"""

from __future__ import annotations

import dataclasses
from typing import Literal

from app.services.hums.fault_signatures import ConditionResult, FaultSignature
from app.services.hums.health_engine import FeatureHealthResult

Severity = Literal["LOW", "MEDIUM", "HIGH"]
Confidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]
CandidateStatus = Literal["CANDIDATE", "SUPPORTED", "WEAK", "UNSUPPORTED"]

REQUIRED_BASE_SCORE = 0.4
SUPPORTING_WEIGHT = 0.5
CONTRADICTING_WEIGHT = 0.3

# Below this score, no candidate is generated at all -- avoids fabricating
# a diagnosis from a single weak, unsupported signal (H4 spec section 39's
# explicit safety requirement).
MIN_SCORE_THRESHOLD = 0.25

_SEVERITY_ORDER: dict[str, int] = {"WATCH": 1, "DEGRADED": 2, "WARNING": 3, "CRITICAL": 3}


@dataclasses.dataclass(frozen=True)
class DiagnosticEvaluation:
    signature: FaultSignature
    required_results: tuple[ConditionResult, ...]
    supporting_results: tuple[ConditionResult, ...]
    contradicting_results: tuple[ConditionResult, ...]
    score: float
    confidence: Confidence
    severity: Severity
    status: CandidateStatus
    explanation: list[str]


def _weighted_ratio(results: tuple[ConditionResult, ...]) -> tuple[float, float]:
    total = sum(r.weight for r in results)
    satisfied = sum(r.weight for r in results if r.satisfied)
    return satisfied, total


def _derive_severity(features: dict[str, FeatureHealthResult], relevant_types: list[str]) -> Severity:
    ranks = [_SEVERITY_ORDER.get(features[ft].state, 0) for ft in relevant_types if ft in features]
    worst = max(ranks) if ranks else 0
    if worst >= 3:
        return "HIGH"
    if worst == 2:
        return "MEDIUM"
    return "LOW"


def _derive_confidence(score: float, feature_confidences: list[str]) -> Confidence:
    if "INSUFFICIENT_DATA" in feature_confidences and all(c == "INSUFFICIENT_DATA" for c in feature_confidences):
        return "INSUFFICIENT_DATA"
    if score >= 0.75:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    return "LOW"


def evaluate_signature(
    signature: FaultSignature, features: dict[str, FeatureHealthResult]
) -> DiagnosticEvaluation | None:
    """Matches one signature against a component's per-feature health
    results. Returns None if required conditions aren't all satisfied, or
    if the resulting score falls below MIN_SCORE_THRESHOLD.
    """
    required_results = tuple(cond(features) for cond in signature.required)
    if not all(r.satisfied for r in required_results):
        return None

    supporting_results = tuple(cond(features) for cond in signature.supporting)
    contradicting_results = tuple(cond(features) for cond in signature.contradicting)

    satisfied_supporting_count = sum(1 for r in supporting_results if r.satisfied)
    if satisfied_supporting_count < signature.minimum_supporting:
        return None

    sup_satisfied_w, sup_total_w = _weighted_ratio(supporting_results)
    con_satisfied_w, con_total_w = _weighted_ratio(contradicting_results)

    score = REQUIRED_BASE_SCORE
    if sup_total_w > 0:
        score += SUPPORTING_WEIGHT * (sup_satisfied_w / sup_total_w)
    if con_total_w > 0:
        score -= CONTRADICTING_WEIGHT * (con_satisfied_w / con_total_w)
    score = max(0.0, min(1.0, score))

    if score < MIN_SCORE_THRESHOLD:
        return None

    relevant_types = [r.feature_type for r in required_results + supporting_results if r.feature_type]
    severity = _derive_severity(features, relevant_types)
    feature_confidences = [features[ft].confidence for ft in relevant_types if ft in features]
    confidence = _derive_confidence(score, feature_confidences)

    status: CandidateStatus = "SUPPORTED" if score >= 0.5 else "WEAK"

    explanation = [f"Required: {r.description} — met." for r in required_results]
    explanation += [f"Supporting: {r.description} — {'met' if r.satisfied else 'not observed'}." for r in supporting_results if r.satisfied]
    if any(r.satisfied for r in contradicting_results):
        explanation += [f"Contradicting: {r.description} — present, reduces confidence." for r in contradicting_results if r.satisfied]

    return DiagnosticEvaluation(
        signature=signature,
        required_results=required_results,
        supporting_results=supporting_results,
        contradicting_results=contradicting_results,
        score=round(score, 4),
        confidence=confidence,
        severity=severity,
        status=status,
        explanation=explanation,
    )


def generate_candidates(
    signatures: tuple[FaultSignature, ...], features: dict[str, FeatureHealthResult]
) -> list[DiagnosticEvaluation]:
    """Evaluates every applicable signature and returns all that matched,
    sorted strongest-first — alternatives are preserved, never collapsed
    to a single "winning" diagnosis (H4 spec section 17).
    """
    evaluations = []
    for sig in signatures:
        result = evaluate_signature(sig, features)
        if result is not None:
            evaluations.append(result)
    return sorted(evaluations, key=lambda e: e.score, reverse=True)


def detect_sensor_fault_candidate(
    sensor_features: dict[str, dict[str, FeatureHealthResult]],
) -> tuple[str, dict[str, FeatureHealthResult]] | None:
    """H4 spec section 20's safeguard: if exactly one sensor on a component
    shows meaningful deterioration while every other sensor on that same
    component reads HEALTHY/WATCH, the anomaly may be the sensor itself,
    not a physical fault. Returns (sensor_id, its features) to build a
    SENSOR_ANOMALY candidate from, or None if this pattern doesn't apply
    (fewer than 2 sensors, or more than one sensor abnormal, which is
    better explained by a shared physical cause).
    """
    if len(sensor_features) < 2:
        return None

    def _worst_state(features: dict[str, FeatureHealthResult]) -> str:
        ranks = {"HEALTHY": 0, "WATCH": 1, "DEGRADED": 2, "WARNING": 3, "CRITICAL": 4}
        worst = "HEALTHY"
        worst_rank = -1
        for f in features.values():
            r = ranks.get(f.state, -1)
            if r > worst_rank:
                worst_rank = r
                worst = f.state
        return worst

    abnormal = [(sid, feats) for sid, feats in sensor_features.items() if _worst_state(feats) in ("DEGRADED", "WARNING", "CRITICAL")]
    healthy = [(sid, feats) for sid, feats in sensor_features.items() if _worst_state(feats) in ("HEALTHY", "WATCH")]

    if len(abnormal) == 1 and len(healthy) >= 1:
        return abnormal[0]
    return None


__all__ = [
    "DiagnosticEvaluation",
    "evaluate_signature",
    "generate_candidates",
    "detect_sensor_fault_candidate",
    "MIN_SCORE_THRESHOLD",
    "REQUIRED_BASE_SCORE",
]
