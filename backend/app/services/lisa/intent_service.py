"""Deterministic intent classification for Lisa's operational investigation
planner. Pure keyword/phrase matching — no LLM call, no guessing. Maps a
question to one of a small, closed set of operational intents the
orchestrator knows how to investigate; anything else is UNKNOWN and falls
through to the existing LLM tool-loop (or the honest provider-unavailable
state) unchanged.
"""

from enum import StrEnum


class Intent(StrEnum):
    AOG = "AOG"
    RELEASE_READINESS = "RELEASE_READINESS"
    TECHNICIAN_AUTHORIZATION = "TECHNICIAN_AUTHORIZATION"
    PROCUREMENT_CHAIN = "PROCUREMENT_CHAIN"  # material / procurement / PO / receiving
    COMPLIANCE = "COMPLIANCE"
    UNKNOWN = "UNKNOWN"


_KEYWORDS: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        Intent.TECHNICIAN_AUTHORIZATION,
        (
            "authorized",
            "authorised",
            "who is assigned",
            "who's assigned",
            "can perform",
            "can they perform",
            "qualified to",
        ),
    ),
    (
        Intent.RELEASE_READINESS,
        (
            "release readiness",
            "release-ready",
            "can we release",
            "be released",
            "block release",
            "release blocked",
            "why can't we release",
            "why cant we release",
        ),
    ),
    (
        Intent.PROCUREMENT_CHAIN,
        (
            "delaying",
            "purchase order",
            " po ",
            " po-",
            " po,",
            " po.",
            " po?",
            "been ordered",
            "supplying",
            "receiv",  # covers receiving/received/receipt
            "outstanding",
            "part missing",
            "missing part",
            "required part",
            "part arrive",
            "arrived",
            "available now",
        ),
    ),
    (
        Intent.COMPLIANCE,
        ("compliant", "compliance"),
    ),
    (
        Intent.AOG,
        ("aog", "grounded", "aircraft on ground"),
    ),
)


def classify_intent(question: str) -> Intent:
    lowered = f" {question.lower()} "
    for intent, phrases in _KEYWORDS:
        if any(phrase in lowered for phrase in phrases):
            return intent
    return Intent.UNKNOWN
