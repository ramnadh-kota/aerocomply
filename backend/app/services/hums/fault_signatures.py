"""H4: Fault signature registry — versioned, in-code, deterministic rules
matching H3 FeatureHealthResult patterns to candidate fault hypotheses.

Why in-code rather than a DB table (per H4 spec section 11's "the exact
schema should be determined after auditing the existing rules
architecture"): the H0 audit found `app/rules_engine/` is an empty stub —
this codebase has no existing DB-driven rule-versioning convention to
extend. Building a full signature-authoring data model for H4 alone, with
no UI or workflow to edit it, would be speculative infrastructure. A
versioned Python registry is deterministic, unit-testable (see
tests/unit/test_hums_diagnostic_engine.py), and each generated
HUMSDiagnosticCandidate records `rule_version` so a row stays reproducible
even after a signature is later revised — see docs/HUMS_DIAGNOSTICS.md for
the extension point if/when a DB-driven editor is actually needed.

These are DEMONSTRATIVE synthetic signatures, not real aerospace
engineering fault-diagnosis criteria for any specific airframe/engine/
component. They exist to prove the architecture, not to certify anything.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Literal

from app.services.hums.health_engine import FeatureHealthResult

ConditionFn = Callable[[dict[str, FeatureHealthResult]], "ConditionResult"]


@dataclasses.dataclass(frozen=True)
class ConditionResult:
    description: str
    satisfied: bool
    feature_type: str | None = None
    weight: float = 1.0


@dataclasses.dataclass(frozen=True)
class FaultSignature:
    fault_code: str
    fault_name: str
    fault_domain: Literal["VIBRATION", "SENSOR"]
    version: str
    description: str
    applicable_measurement_types: tuple[str, ...]
    required: tuple[ConditionFn, ...]
    supporting: tuple[ConditionFn, ...]
    contradicting: tuple[ConditionFn, ...] = ()
    minimum_supporting: int = 1


# --- Condition builders -----------------------------------------------------
# Each returns a ConditionFn closed over a feature_type + the deviation/
# trend property it inspects, so signatures read as a declarative list
# rather than ad-hoc lambdas scattered through matching logic.


def _deviation_at_least(feature_type: str, *, min_state_rank: int, weight: float = 1.0) -> ConditionFn:
    order = {"NORMAL": 0, "ELEVATED": 1, "DEVIATED": 2, "SEVERE": 3}

    def _check(features: dict[str, FeatureHealthResult]) -> ConditionResult:
        result = features.get(feature_type)
        desc = f"{feature_type} deviation >= {[k for k, v in order.items() if v == min_state_rank][0]}"
        if result is None or result.deviation is None or result.deviation.state == "INSUFFICIENT_DATA":
            return ConditionResult(desc, False, feature_type, weight)
        satisfied = order.get(result.deviation.state, -1) >= min_state_rank
        return ConditionResult(desc, satisfied, feature_type, weight)

    return _check


def _deviation_below(feature_type: str, *, max_state_rank: int, weight: float = 1.0) -> ConditionFn:
    order = {"NORMAL": 0, "ELEVATED": 1, "DEVIATED": 2, "SEVERE": 3}

    def _check(features: dict[str, FeatureHealthResult]) -> ConditionResult:
        result = features.get(feature_type)
        desc = f"{feature_type} deviation <= {[k for k, v in order.items() if v == max_state_rank][0]} (not itself elevated)"
        if result is None or result.deviation is None or result.deviation.state == "INSUFFICIENT_DATA":
            return ConditionResult(desc, False, feature_type, weight)
        satisfied = order.get(result.deviation.state, 99) <= max_state_rank
        return ConditionResult(desc, satisfied, feature_type, weight)

    return _check


def _trend_worsening(feature_type: str, *, weight: float = 1.0) -> ConditionFn:
    def _check(features: dict[str, FeatureHealthResult]) -> ConditionResult:
        result = features.get(feature_type)
        desc = f"{feature_type} trend increasing/accelerating"
        if result is None or result.trend is None:
            return ConditionResult(desc, False, feature_type, weight)
        satisfied = result.trend.direction in ("INCREASING", "ACCELERATING")
        return ConditionResult(desc, satisfied, feature_type, weight)

    return _check


def _persistent(feature_type: str, *, min_count: int, weight: float = 1.0) -> ConditionFn:
    def _check(features: dict[str, FeatureHealthResult]) -> ConditionResult:
        result = features.get(feature_type)
        desc = f"{feature_type} persistently deviated for >= {min_count} consecutive observations"
        if result is None:
            return ConditionResult(desc, False, feature_type, weight)
        satisfied = result.consecutive_deviation_count >= min_count
        return ConditionResult(desc, satisfied, feature_type, weight)

    return _check


# --- Signature registry -----------------------------------------------------
# fault_code convention: "<DOMAIN>-<SHORT>-<NNN>" (mirrors HUMS_* signal_type
# naming already used elsewhere in this codebase).

BEARING_DEGRADATION = FaultSignature(
    fault_code="VIB-BRG-001",
    fault_name="Possible bearing degradation",
    fault_domain="VIBRATION",
    version="1.0",
    description=(
        "Elevated vibration RMS together with elevated kurtosis (impulsive/spiky waveform shape, "
        "characteristic of early bearing spall/pitting in demonstrative signal-processing literature) "
        "is treated as a candidate bearing-degradation signature."
    ),
    applicable_measurement_types=("vibration",),
    required=(
        _deviation_at_least("rms", min_state_rank=2),  # DEVIATED or SEVERE
        _deviation_at_least("kurtosis", min_state_rank=2),
    ),
    supporting=(
        _deviation_at_least("crest_factor", min_state_rank=1, weight=0.5),
        _trend_worsening("rms", weight=1.0),
        _persistent("rms", min_count=3, weight=1.0),
    ),
    contradicting=(),
    minimum_supporting=1,
)

ROTOR_IMBALANCE = FaultSignature(
    fault_code="VIB-IMB-001",
    fault_name="Possible rotor imbalance",
    fault_domain="VIBRATION",
    version="1.0",
    description=(
        "Elevated vibration RMS with a smooth (non-impulsive) waveform — kurtosis staying near normal — "
        "is treated as a candidate rotor-imbalance signature, distinct from and competing with bearing "
        "degradation (which expects kurtosis to also be elevated)."
    ),
    applicable_measurement_types=("vibration",),
    required=(_deviation_at_least("rms", min_state_rank=2),),
    supporting=(
        _trend_worsening("rms", weight=1.0),
        _persistent("rms", min_count=2, weight=0.5),
    ),
    contradicting=(_deviation_at_least("kurtosis", min_state_rank=2, weight=1.0),),
    minimum_supporting=1,
)

VIBRATION_SIGNATURES: tuple[FaultSignature, ...] = (BEARING_DEGRADATION, ROTOR_IMBALANCE)

SIGNATURE_REGISTRY: dict[str, FaultSignature] = {s.fault_code: s for s in VIBRATION_SIGNATURES}


__all__ = [
    "ConditionResult",
    "FaultSignature",
    "BEARING_DEGRADATION",
    "ROTOR_IMBALANCE",
    "VIBRATION_SIGNATURES",
    "SIGNATURE_REGISTRY",
]
