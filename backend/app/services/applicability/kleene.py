"""Deterministic Three-Valued (Kleene) Logic for Aerospace Applicability.

Domain Invariant (docs/ontology/DOMAIN_INVARIANTS.md #23):
"UNKNOWN is not FALSE". Missing configuration, incomplete records, or unconfirmed
modifications must evaluate to UNKNOWN / INSUFFICIENT_DATA and must NEVER silently
collapse into FALSE or NOT_APPLICABLE.

Truth Tables:
AND:
  TRUE  AND TRUE    = TRUE
  TRUE  AND FALSE   = FALSE
  TRUE  AND UNKNOWN = UNKNOWN
  FALSE AND UNKNOWN = FALSE
  UNKNOWN AND UNKNOWN = UNKNOWN

OR:
  TRUE  OR TRUE    = TRUE
  TRUE  OR FALSE   = TRUE
  TRUE  OR UNKNOWN = TRUE
  FALSE OR UNKNOWN = UNKNOWN
  UNKNOWN OR UNKNOWN = UNKNOWN

NOT:
  NOT TRUE    = FALSE
  NOT FALSE   = TRUE
  NOT UNKNOWN = UNKNOWN
"""

from collections.abc import Iterable
from enum import Enum


class KleeneValue(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

    def __repr__(self) -> str:
        return f"KleeneValue.{self.value}"

    def __str__(self) -> str:
        return self.value


def to_kleene(val: KleeneValue | str | bool | None) -> KleeneValue:
    """Coerce supported types into a canonical KleeneValue.

    Raises ValueError on unrecognized or invalid representations.
    None represents missing data and is coerced to UNKNOWN.
    """
    if isinstance(val, KleeneValue):
        return val
    if val is None:
        return KleeneValue.UNKNOWN
    if isinstance(val, bool):
        return KleeneValue.TRUE if val else KleeneValue.FALSE
    if isinstance(val, str):
        normalized = val.strip().upper()
        if normalized == "TRUE":
            return KleeneValue.TRUE
        if normalized == "FALSE":
            return KleeneValue.FALSE
        if normalized in ("UNKNOWN", "INSUFFICIENT_DATA", "INDETERMINATE"):
            return KleeneValue.UNKNOWN
        raise ValueError(f"Cannot coerce string {val!r} to KleeneValue")
    raise TypeError(f"Unsupported type {type(val)!r} for Kleene conversion")


def kleene_and(a: KleeneValue | str | bool | None, b: KleeneValue | str | bool | None) -> KleeneValue:
    """Compute binary Kleene conjunction (AND).

    Semantics:
      - If either operand is FALSE, the conjunction is definitively FALSE.
      - If either operand is UNKNOWN (and neither is FALSE), the outcome cannot be
        guaranteed and is UNKNOWN.
      - If both operands are TRUE, the outcome is TRUE.
    """
    val_a = to_kleene(a)
    val_b = to_kleene(b)

    if val_a is KleeneValue.FALSE or val_b is KleeneValue.FALSE:
        return KleeneValue.FALSE
    if val_a is KleeneValue.UNKNOWN or val_b is KleeneValue.UNKNOWN:
        return KleeneValue.UNKNOWN
    return KleeneValue.TRUE


def kleene_or(a: KleeneValue | str | bool | None, b: KleeneValue | str | bool | None) -> KleeneValue:
    """Compute binary Kleene disjunction (OR).

    Semantics:
      - If either operand is TRUE, the disjunction is definitively TRUE.
      - If either operand is UNKNOWN (and neither is TRUE), the outcome cannot be
        guaranteed and is UNKNOWN.
      - If both operands are FALSE, the outcome is FALSE.
    """
    val_a = to_kleene(a)
    val_b = to_kleene(b)

    if val_a is KleeneValue.TRUE or val_b is KleeneValue.TRUE:
        return KleeneValue.TRUE
    if val_a is KleeneValue.UNKNOWN or val_b is KleeneValue.UNKNOWN:
        return KleeneValue.UNKNOWN
    return KleeneValue.FALSE


def kleene_not(val: KleeneValue | str | bool | None) -> KleeneValue:
    """Compute unary Kleene negation (NOT).

    Semantics:
      - NOT TRUE = FALSE
      - NOT FALSE = TRUE
      - NOT UNKNOWN = UNKNOWN
    """
    k_val = to_kleene(val)
    if k_val is KleeneValue.UNKNOWN:
        return KleeneValue.UNKNOWN
    if k_val is KleeneValue.TRUE:
        return KleeneValue.FALSE
    return KleeneValue.TRUE


def kleene_and_all(
    operands: Iterable[KleeneValue | str | bool | None],
    *,
    empty_default: KleeneValue = KleeneValue.TRUE,
) -> KleeneValue:
    """Reduce an iterable of operands under Kleene AND.

    Conjunction over an empty collection yields empty_default (default TRUE,
    the Boolean identity for conjunction).
    """
    result = empty_default
    for op in operands:
        result = kleene_and(result, op)
        if result is KleeneValue.FALSE:
            # Short-circuit: FALSE is an absorbing element for Kleene AND
            return KleeneValue.FALSE
    return result


def kleene_or_all(
    operands: Iterable[KleeneValue | str | bool | None],
    *,
    empty_default: KleeneValue = KleeneValue.FALSE,
) -> KleeneValue:
    """Reduce an iterable of operands under Kleene OR.

    Disjunction over an empty collection yields empty_default (default FALSE,
    the Boolean identity for disjunction).
    """
    result = empty_default
    for op in operands:
        result = kleene_or(result, op)
        if result is KleeneValue.TRUE:
            # Short-circuit: TRUE is an absorbing element for Kleene OR
            return KleeneValue.TRUE
    return result
