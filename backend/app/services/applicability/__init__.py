"""Applicability domain service package for KOTA Aerospace / AeroComply platform.
Governs aerospace applicability rules, hierarchical condition trees, deterministic
three-valued (Kleene) logic, and immutable evaluation snapshots.
"""

from app.services.applicability.evaluation_service import (
    create_rule,
    evaluate_applicability,
    get_rule,
    list_rules,
)
from app.services.applicability.kleene import (
    KleeneValue,
    kleene_and,
    kleene_and_all,
    kleene_not,
    kleene_or,
    kleene_or_all,
    to_kleene,
)

__all__ = [
    "KleeneValue",
    "kleene_and",
    "kleene_or",
    "kleene_not",
    "kleene_and_all",
    "kleene_or_all",
    "to_kleene",
    "create_rule",
    "get_rule",
    "list_rules",
    "evaluate_applicability",
]
