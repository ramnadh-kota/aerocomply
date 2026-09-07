"""Deterministic safety layer for the Lisa agent.

Ported (pattern list, not code) from the frontend engine's
AIRWORTHINESS_GUARD_PATTERNS (frontend/lib/mock/ai/engine.ts) — the same
airworthiness/release/certification/safety-gate-bypass phrasings are
refused here too, in plain Python, so a real LLM configured later cannot
talk its way around the refusal via prompt engineering or by paraphrasing
the question. This check runs OUTSIDE the model:

1. Against the raw user question, before any tool call or model call.
2. Against tool results, before they are handed to the model for synthesis
   (so the model is never even shown a hint of a release/airworthiness
   determination cue that isn't there).
3. Against the model's own final synthesized text, before it is returned to
   the caller — a final backstop in case the model produces refusal-worthy
   language on its own initiative.

Never rely on a system prompt alone for this — the system prompt asks the
model to refuse, but this module is what actually enforces it.
"""

from __future__ import annotations

import re

AIRWORTHINESS_GUARD_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bairworth", re.IGNORECASE),
    re.compile(r"\bsafe to dispatch\b", re.IGNORECASE),
    re.compile(r"\bsafe to fly\b", re.IGNORECASE),
    re.compile(r"\bapproved substitute\b", re.IGNORECASE),
    re.compile(r"\blegally (complete|compliant|authorized)\b", re.IGNORECASE),
    re.compile(r"\bcertificate of release\b", re.IGNORECASE),
    re.compile(r"\bcrs\b", re.IGNORECASE),
    re.compile(r"\brelease( it| the aircraft)? to service\b", re.IGNORECASE),
    re.compile(r"\b(can|could|should|may) we release (this|the|that) aircraft\b", re.IGNORECASE),
    re.compile(r"\brelease (this|the|that) aircraft\b", re.IGNORECASE),
    re.compile(r"\b(this|the|that) aircraft (be|get) released\b", re.IGNORECASE),
    re.compile(r"\baircraft be released\b", re.IGNORECASE),
    re.compile(
        r"\b(skip|bypass|override|waive|get around)\b[^.?!]{0,40}"
        r"\b(inspection|rii|independent inspection|evidence|safety gate|checklist"
        r"|sign[\s-]?off|signoff)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(inspection|rii|independent inspection|evidence|safety gate|checklist"
        r"|sign[\s-]?off|signoff)\b"
        r"[^.?!]{0,40}\b(skip|bypass|override|waive)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\brelease\b[^.?!]{0,40}\bwithout\b[^.?!]{0,20}"
        r"\b(rii|inspection|independent inspection|evidence|sign[\s-]?off|signoff)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\brelease\b[^.?!]{0,40}\bdespite\b",
        re.IGNORECASE,
    ),
]

SAFETY_REFUSAL_HEADLINE = "SAFETY_REFUSAL — this requires authorized maintenance personnel"

SAFETY_REFUSAL_NARRATIVE = [
    "SAFETY_REFUSAL: I cannot determine airworthiness, legal compliance, or certification of "
    "release — those are determinations for authorized maintenance personnel using applicable "
    "approved data and procedures, not this system.",
    "The system can summarize recorded facts: aircraft/work order status, open safety gates, "
    "and open discrepancies.",
    "Ask about a specific aircraft or work order's recorded execution state, safety gates, or "
    "open discrepancies, and I can summarize what the current data shows.",
]


def is_safety_restricted(text: str) -> bool:
    """True if `text` asks for (or, for a would-be answer, contains) an
    airworthiness/release/certification determination or a request to
    bypass a safety gate."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in AIRWORTHINESS_GUARD_PATTERNS)


def safety_refusal_response() -> dict:
    """The forced-override response shape, matching the AiResponse fields
    used by the frontend's own airworthiness guard branch."""
    return {
        "headline": SAFETY_REFUSAL_HEADLINE,
        "narrative": list(SAFETY_REFUSAL_NARRATIVE),
        "priority": "CRITICAL",
        "whatIFound": [
            "This question asks Lisa to make or imply an airworthiness, release, or "
            "legal-compliance determination."
        ],
        "whyItMatters": (
            "Airworthiness and release-to-service decisions carry direct flight-safety and "
            "regulatory consequences — they must be made by authorized maintenance personnel "
            "applying approved data, not inferred by this system."
        ),
        "recommendedNextStep": (
            "Ask about the recorded execution state, open safety gates, or open discrepancies "
            "for a specific aircraft or work order instead — Lisa can summarize those facts."
        ),
        "dependencies": [],
        "whoShouldAct": (
            "Authorized maintenance personnel (Quality / Airworthiness Release Signatory)"
        ),
        "relatedRecords": [],
        "confidenceState": "CONFIRMED",
        "actionCategory": "SAFETY_RESTRICTED",
    }
