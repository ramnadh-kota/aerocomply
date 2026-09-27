"""Unit tests for deterministic 3-valued (Kleene) logic.

Critical domain invariants:
- UNKNOWN != FALSE (docs/ontology/DOMAIN_INVARIANTS.md #23)
- Incomplete/missing configuration must never silently evaluate to FALSE or NOT_APPLICABLE.
- Pure and deterministic evaluation.
"""

import pytest

from app.services.applicability.kleene import (
    KleeneValue,
    kleene_and,
    kleene_and_all,
    kleene_not,
    kleene_or,
    kleene_or_all,
    to_kleene,
)


class TestKleenePrimitiveTruthTables:
    """Validate standard Kleene 3-valued logic truth tables."""

    def test_and_truth_table(self):
        T = KleeneValue.TRUE
        F = KleeneValue.FALSE
        U = KleeneValue.UNKNOWN

        # TRUE AND *
        assert kleene_and(T, T) == T
        assert kleene_and(T, F) == F
        assert kleene_and(T, U) == U

        # FALSE AND *
        assert kleene_and(F, T) == F
        assert kleene_and(F, F) == F
        assert kleene_and(F, U) == F

        # UNKNOWN AND *
        assert kleene_and(U, T) == U
        assert kleene_and(U, F) == F
        assert kleene_and(U, U) == U

    def test_or_truth_table(self):
        T = KleeneValue.TRUE
        F = KleeneValue.FALSE
        U = KleeneValue.UNKNOWN

        # TRUE OR *
        assert kleene_or(T, T) == T
        assert kleene_or(T, F) == T
        assert kleene_or(T, U) == T

        # FALSE OR *
        assert kleene_or(F, T) == T
        assert kleene_or(F, F) == F
        assert kleene_or(F, U) == U

        # UNKNOWN OR *
        assert kleene_or(U, T) == T
        assert kleene_or(U, F) == U
        assert kleene_or(U, U) == U

    def test_not_truth_table(self):
        T = KleeneValue.TRUE
        F = KleeneValue.FALSE
        U = KleeneValue.UNKNOWN

        assert kleene_not(T) == F
        assert kleene_not(F) == T
        assert kleene_not(U) == U


class TestDomainInvariantUnknownNotFalse:
    """Crucial domain invariant: UNKNOWN must never be treated as FALSE."""

    def test_unknown_is_not_equal_to_false(self):
        assert KleeneValue.UNKNOWN != KleeneValue.FALSE
        assert KleeneValue.UNKNOWN != False  # noqa: E712
        assert KleeneValue.FALSE != KleeneValue.UNKNOWN

    def test_unknown_does_not_absorb_like_false_in_and(self):
        # In standard 2-valued logic, if missing info was treated as False:
        # TRUE AND FALSE = FALSE.
        # But in 3-valued logic:
        # TRUE AND UNKNOWN = UNKNOWN, preserving uncertainty.
        assert kleene_and(KleeneValue.TRUE, KleeneValue.UNKNOWN) == KleeneValue.UNKNOWN
        assert kleene_and(KleeneValue.TRUE, KleeneValue.UNKNOWN) != KleeneValue.FALSE

    def test_unknown_does_not_absorb_like_false_in_or(self):
        # In standard 2-valued logic: FALSE OR FALSE = FALSE.
        # But if one is unknown: FALSE OR UNKNOWN = UNKNOWN.
        assert kleene_or(KleeneValue.FALSE, KleeneValue.UNKNOWN) == KleeneValue.UNKNOWN
        assert kleene_or(KleeneValue.FALSE, KleeneValue.UNKNOWN) != KleeneValue.FALSE

    def test_negation_of_unknown_is_not_true(self):
        # In standard 2-valued logic: NOT FALSE = TRUE.
        # If UNKNOWN were treated as FALSE, NOT UNKNOWN would become TRUE!
        # This would cause non-applicable requirements to falsely become applicable!
        assert kleene_not(KleeneValue.UNKNOWN) == KleeneValue.UNKNOWN
        assert kleene_not(KleeneValue.UNKNOWN) != KleeneValue.TRUE


class TestCoercionAndEdgeCases:
    """Test to_kleene coercion and handling of missing/invalid inputs."""

    def test_coercion_from_bool(self):
        assert to_kleene(True) == KleeneValue.TRUE
        assert to_kleene(False) == KleeneValue.FALSE

    def test_coercion_from_none_is_unknown(self):
        # Missing configuration data maps to UNKNOWN
        assert to_kleene(None) == KleeneValue.UNKNOWN

    def test_coercion_from_strings(self):
        assert to_kleene("TRUE") == KleeneValue.TRUE
        assert to_kleene("true") == KleeneValue.TRUE
        assert to_kleene("FALSE") == KleeneValue.FALSE
        assert to_kleene("false") == KleeneValue.FALSE
        assert to_kleene("UNKNOWN") == KleeneValue.UNKNOWN
        assert to_kleene("unknown") == KleeneValue.UNKNOWN
        assert to_kleene("INSUFFICIENT_DATA") == KleeneValue.UNKNOWN

    def test_invalid_coercion_raises(self):
        with pytest.raises(ValueError, match="Cannot coerce string"):
            to_kleene("MAYBE")
        with pytest.raises(TypeError, match="Unsupported type"):
            to_kleene(123)


class TestMultiOperandReducers:
    """Test kleene_and_all and kleene_or_all."""

    def test_and_all_empty(self):
        # Conjunction identity is TRUE
        assert kleene_and_all([]) == KleeneValue.TRUE

    def test_and_all_all_true(self):
        assert kleene_and_all([KleeneValue.TRUE, KleeneValue.TRUE, KleeneValue.TRUE]) == KleeneValue.TRUE

    def test_and_all_with_unknown(self):
        assert kleene_and_all([KleeneValue.TRUE, KleeneValue.UNKNOWN, KleeneValue.TRUE]) == KleeneValue.UNKNOWN

    def test_and_all_with_false_short_circuits(self):
        # Even with UNKNOWN, FALSE definitively fails the conjunction
        assert (
            kleene_and_all([KleeneValue.TRUE, KleeneValue.UNKNOWN, KleeneValue.FALSE, KleeneValue.TRUE])
            == KleeneValue.FALSE
        )

    def test_or_all_empty(self):
        # Disjunction identity is FALSE
        assert kleene_or_all([]) == KleeneValue.FALSE

    def test_or_all_all_false(self):
        assert kleene_or_all([KleeneValue.FALSE, KleeneValue.FALSE]) == KleeneValue.FALSE

    def test_or_all_with_unknown(self):
        assert kleene_or_all([KleeneValue.FALSE, KleeneValue.UNKNOWN, KleeneValue.FALSE]) == KleeneValue.UNKNOWN

    def test_or_all_with_true_short_circuits(self):
        # Even with UNKNOWN, TRUE definitively satisfies the disjunction
        assert (
            kleene_or_all([KleeneValue.FALSE, KleeneValue.UNKNOWN, KleeneValue.TRUE, KleeneValue.FALSE])
            == KleeneValue.TRUE
        )


class TestNestedExpressions:
    """Verify behavior on complex nested condition trees."""

    def test_nested_conjunction_with_unknown(self):
        # (AIRCRAFT_VARIANT == A320 [TRUE]) AND (MSN in 1000..2000 [UNKNOWN]) AND (ENGINE == CFM56 [TRUE])
        # Result must be UNKNOWN
        variant = KleeneValue.TRUE
        msn = KleeneValue.UNKNOWN
        engine = KleeneValue.TRUE

        expr = kleene_and(kleene_and(variant, msn), engine)
        assert expr == KleeneValue.UNKNOWN

    def test_nested_disjunction_over_unknown(self):
        # (ENGINE == CFM56 [UNKNOWN]) OR (ENGINE == LEAP-1A [TRUE])
        # Since second is TRUE, entire expression is TRUE
        engine_1 = KleeneValue.UNKNOWN
        engine_2 = KleeneValue.TRUE

        expr = kleene_or(engine_1, engine_2)
        assert expr == KleeneValue.TRUE

    def test_nested_de_morgans_laws(self):
        # NOT (A AND B) == (NOT A) OR (NOT B)
        # Check across all combinations of T, F, U
        values = [KleeneValue.TRUE, KleeneValue.FALSE, KleeneValue.UNKNOWN]
        for a in values:
            for b in values:
                lhs = kleene_not(kleene_and(a, b))
                rhs = kleene_or(kleene_not(a), kleene_not(b))
                assert lhs == rhs, f"De Morgan's failure on a={a}, b={b}"

        # NOT (A OR B) == (NOT A) AND (NOT B)
        for a in values:
            for b in values:
                lhs = kleene_not(kleene_or(a, b))
                rhs = kleene_and(kleene_not(a), kleene_not(b))
                assert lhs == rhs, f"De Morgan's failure on a={a}, b={b}"

    def test_deterministic_reproducibility(self):
        # Given identical inputs, result must be identical across 100 iterations
        for _ in range(100):
            res = kleene_and(
                kleene_or(KleeneValue.FALSE, KleeneValue.UNKNOWN),
                kleene_not(KleeneValue.UNKNOWN),
            )
            assert res == KleeneValue.UNKNOWN
