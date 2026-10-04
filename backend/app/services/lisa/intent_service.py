"""Deterministic intent classification for Lisa's operational investigation
planner. Pure keyword/phrase matching — no LLM call, no guessing. Maps a
question to one of a small, closed set of operational intents the
orchestrator knows how to investigate; anything else is UNKNOWN and falls
through to the existing LLM tool-loop (or the honest provider-unavailable
state) unchanged.
"""

from enum import StrEnum


class Intent(StrEnum):
    FLEET_CORRELATION = "FLEET_CORRELATION"
    AOG = "AOG"
    RELEASE_READINESS = "RELEASE_READINESS"
    TECHNICIAN_AUTHORIZATION = "TECHNICIAN_AUTHORIZATION"
    PROCUREMENT_CHAIN = "PROCUREMENT_CHAIN"  # material / procurement / PO / receiving
    COMPLIANCE = "COMPLIANCE"
    ASSESSMENT = "ASSESSMENT"
    PROACTIVE_INTELLIGENCE = "PROACTIVE_INTELLIGENCE"
    TELEMETRY_HUMS = "TELEMETRY_HUMS"
    UNKNOWN = "UNKNOWN"


_KEYWORDS: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        Intent.FLEET_CORRELATION,
        (
            "fleet correlation",
            "fleet correlations",
            "cross-asset correlation",
            "cross asset correlation",
            "cross-asset",
            "cross asset",
            "similar vibration",
            "similar exceedance",
            "similar exceedances",
            "similar hums",
            "similar anomaly",
            "similar anomalies",
            "vibration anomalies",
            "vibration anomaly",
            "vibration spikes",
            "repeated vibration",
            "multiple assets showing",
            "across multiple assets",
            "fleet anomaly",
            "fleet anomalies",
            "correlated anomalies",
            "correlated anomaly",
            "fleet signals",
            "fleet signal",
            "supports this correlation",
            "supports this fleet correlation",
            "evidence supports this",
            "supporting evidence",
            "require engineering review",
            "requires engineering review",
            "isolated or recurring",
            "health patterns over",
            "fleet's health patterns",
            "fleet health patterns",
        ),
    ),
    (
        Intent.TELEMETRY_HUMS,

        (
            "telemetry",
            "hums",
            "flighthub",
            "sensor reading",
            "sensor readings",
            "sensor health",
            "vibration exceedance",
            "vibration reading",
            "motor temperature",
            "battery health",
            "latest telemetry",
            "telemetry event",
            "telemetry status",
            "health intelligence",
        ),
    ),
    (
        Intent.PROACTIVE_INTELLIGENCE,
        (
            "what needs attention",
            "needs attention today",
            "needs attention",
            "proactive alert",
            "proactive alerts",
            "emerging risk",
            "emerging risks",
            "approaching maintenance",
            "approaching threshold",
            "upcoming inspection",
            "upcoming inspections",
            "recurring finding",
            "recurring findings",
            "evidence gap",
            "evidence gaps",
            "high priority",
            "readiness degradation",
            "proactive intelligence",
            "attention required",
        ),
    ),
    (
        Intent.ASSESSMENT,
        (
            "biggest risk",
            "biggest gap",
            "operational risk",
            "what should we improve",
            "highest impact",
            "highest priority",
            "highest risk",
            "most complex",
            "top recommendation",
            "recommendations",
            "roadmap",
            "run an assessment",
            "run assessment",
            "assessment",
            "what changed since",
            "compare the latest",
            "compare assessment",
            "previous assessment",
            "previous snapshot",
        ),
    ),
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
