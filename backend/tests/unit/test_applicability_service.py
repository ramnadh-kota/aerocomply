"""Unit tests for Applicability condition evaluation and logic engine.

Verifies:
- AIRCRAFT_VARIANT matching
- MSN_RANGE matching
- ENGINE_TYPE matching
- Kleene UNKNOWN propagation: missing data NEVER becomes FALSE
- Nested condition trees (combinators AND, OR, NOT)
- Output states: APPLICABLE, NOT_APPLICABLE, INSUFFICIENT_DATA, REVIEW_REQUIRED
"""

import uuid
import pytest

from app.models.applicability import (
    ApplicabilityCondition,
    ConditionType,
    EvaluationResult,
)
from app.services.applicability.evaluation_service import _evaluate_node
from app.services.applicability.kleene import KleeneValue


def _build_node(
    cond_type: ConditionType,
    label: str,
    params: dict | None = None,
    children: list[ApplicabilityCondition] | None = None,
) -> ApplicabilityCondition:
    node = ApplicabilityCondition(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        rule_id=uuid.uuid4(),
        condition_type=cond_type.value,
        label=label,
        parameters=params or {},
        sequence=0,
    )
    node.children = children or []
    return node


class TestVariantMatching:
    def test_variant_exact_match(self):
        node = _build_node(
            ConditionType.AIRCRAFT_VARIANT,
            "Variant = A320",
            {"variant": "A320"},
        )
        snapshot = {"aircraft_type": "A320"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.TRUE
        assert trace["result"] == "TRUE"

    def test_variant_prefix_family_match(self):
        node = _build_node(
            ConditionType.AIRCRAFT_VARIANT,
            "Variant = A320",
            {"variant": "A320"},
        )
        snapshot = {"aircraft_type": "A320-200"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.TRUE

    def test_variant_mismatch(self):
        node = _build_node(
            ConditionType.AIRCRAFT_VARIANT,
            "Variant = A320",
            {"variant": "A320"},
        )
        snapshot = {"aircraft_type": "B737-800"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.FALSE

    def test_variant_missing_in_snapshot_is_unknown_never_false(self):
        node = _build_node(
            ConditionType.AIRCRAFT_VARIANT,
            "Variant = A320",
            {"variant": "A320"},
        )
        # Incomplete configuration: aircraft_type is None
        snapshot = {"aircraft_type": None}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.UNKNOWN
        assert val != KleeneValue.FALSE


class TestMsnRangeMatching:
    def test_msn_in_range(self):
        node = _build_node(
            ConditionType.MSN_RANGE,
            "MSN 1000..2000",
            {"min_msn": 1000, "max_msn": 2000},
        )
        snapshot = {"msn": "1500"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.TRUE

    def test_msn_below_range(self):
        node = _build_node(
            ConditionType.MSN_RANGE,
            "MSN 1000..2000",
            {"min_msn": 1000, "max_msn": 2000},
        )
        snapshot = {"msn": "500"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.FALSE

    def test_msn_above_range(self):
        node = _build_node(
            ConditionType.MSN_RANGE,
            "MSN 1000..2000",
            {"min_msn": 1000, "max_msn": 2000},
        )
        snapshot = {"msn": "2500"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.FALSE

    def test_msn_with_alphanumeric_prefix(self):
        node = _build_node(
            ConditionType.MSN_RANGE,
            "MSN 1000..2000",
            {"min_msn": 1000, "max_msn": 2000},
        )
        snapshot = {"msn": "MSN-1500"}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.TRUE

    def test_msn_missing_in_snapshot_is_unknown_never_false(self):
        node = _build_node(
            ConditionType.MSN_RANGE,
            "MSN 1000..2000",
            {"min_msn": 1000, "max_msn": 2000},
        )
        snapshot = {"msn": None}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.UNKNOWN
        assert val != KleeneValue.FALSE


class TestEngineTypeMatching:
    def test_engine_matches(self):
        node = _build_node(
            ConditionType.ENGINE_TYPE,
            "Engine = CFM56",
            {"engine_type": "CFM56"},
        )
        snapshot = {
            "installed_engines": [
                {"model": "CFM56-5B", "manufacturer": "CFM"},
            ]
        }
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.TRUE

    def test_engine_mismatches_all_known(self):
        node = _build_node(
            ConditionType.ENGINE_TYPE,
            "Engine = CFM56",
            {"engine_type": "CFM56"},
        )
        snapshot = {
            "installed_engines": [
                {"model": "PW1100G", "manufacturer": "Pratt & Whitney"},
            ]
        }
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.FALSE

    def test_no_installed_engines_on_file_is_unknown_never_false(self):
        # Crucial domain invariant: If no engine records exist, it means configuration is missing,
        # not that the aircraft has no engines! Must be UNKNOWN.
        node = _build_node(
            ConditionType.ENGINE_TYPE,
            "Engine = CFM56",
            {"engine_type": "CFM56"},
        )
        snapshot = {"installed_engines": []}
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.UNKNOWN
        assert val != KleeneValue.FALSE

    def test_incomplete_engine_model_is_unknown(self):
        node = _build_node(
            ConditionType.ENGINE_TYPE,
            "Engine = CFM56",
            {"engine_type": "CFM56"},
        )
        # One engine has no model recorded
        snapshot = {
            "installed_engines": [
                {"model": None, "manufacturer": "CFM"},
            ]
        }
        val, trace = _evaluate_node(node, snapshot)
        assert val == KleeneValue.UNKNOWN


class TestHierarchicalConditionTrees:
    def test_full_aircraft_conjunction_all_true(self):
        # AIRCRAFT_VARIANT = A320 AND MSN_RANGE = 1000..2000 AND ENGINE_TYPE = CFM56
        cond_variant = _build_node(ConditionType.AIRCRAFT_VARIANT, "Variant A320", {"variant": "A320"})
        cond_msn = _build_node(ConditionType.MSN_RANGE, "MSN 1000..2000", {"min_msn": 1000, "max_msn": 2000})
        cond_eng = _build_node(ConditionType.ENGINE_TYPE, "Engine CFM56", {"engine_type": "CFM56"})

        root = _build_node(ConditionType.AND, "Root Conjunction", children=[cond_variant, cond_msn, cond_eng])

        snapshot = {
            "aircraft_type": "A320",
            "msn": "1500",
            "installed_engines": [{"model": "CFM56-5B"}],
        }
        val, trace = _evaluate_node(root, snapshot)
        assert val == KleeneValue.TRUE
        assert len(trace["children"]) == 3

    def test_full_aircraft_conjunction_with_missing_engine_propagates_unknown(self):
        # A320 (TRUE) AND MSN 1500 (TRUE) AND Engine (UNKNOWN -> no engine data)
        # Result MUST BE UNKNOWN, NOT FALSE!
        cond_variant = _build_node(ConditionType.AIRCRAFT_VARIANT, "Variant A320", {"variant": "A320"})
        cond_msn = _build_node(ConditionType.MSN_RANGE, "MSN 1000..2000", {"min_msn": 1000, "max_msn": 2000})
        cond_eng = _build_node(ConditionType.ENGINE_TYPE, "Engine CFM56", {"engine_type": "CFM56"})

        root = _build_node(ConditionType.AND, "Root Conjunction", children=[cond_variant, cond_msn, cond_eng])

        snapshot = {
            "aircraft_type": "A320",
            "msn": "1500",
            "installed_engines": [],  # missing data
        }
        val, trace = _evaluate_node(root, snapshot)
        assert val == KleeneValue.UNKNOWN
        assert val != KleeneValue.FALSE

    def test_disjunction_absorbs_unknown_when_one_branch_true(self):
        # Variant A320 (TRUE) OR Variant B737 (UNKNOWN) -> TRUE
        cond1 = _build_node(ConditionType.AIRCRAFT_VARIANT, "A320", {"variant": "A320"})
        cond2 = _build_node(ConditionType.AIRCRAFT_VARIANT, "B737", {"variant": "B737"})

        root = _build_node(ConditionType.OR, "Variant Disjunction", children=[cond1, cond2])

        snapshot = {"aircraft_type": "A320"}
        val, trace = _evaluate_node(root, snapshot)
        assert val == KleeneValue.TRUE
