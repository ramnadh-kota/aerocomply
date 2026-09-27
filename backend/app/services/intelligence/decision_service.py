"""D2.2 Pass 2 -- Decision Engine.

Consumes -- never re-derives -- app/services/intelligence/
priority_intelligence_service.py (which itself consumes Pass-1 readiness and
risk intelligence, plus D2-4's warnings). This module runs no domain
queries of its own; every field is a deterministic classification of
priority_intelligence's own output.

This is NOT a recommendation engine (D2.2 Pass 3) and NOT an autonomous
action engine. It never mutates operational, compliance, evidence, or
readiness state, never calls an LLM, and never prescribes a specific
maintenance action -- it only classifies "what decision state follows from
the current priority/readiness/risk picture" into one of five deterministic
states, distinct from both the D2-4 intelligence-state vocabulary
(NOMINAL/DEGRADED/RESTRICTED/GROUNDED_INTEL/UNKNOWN_INTEL, "what is true")
and the risk/priority tier vocabulary (CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN,
"how severe").

decision_state derivation (deterministic rule table, evaluated in order):
  1. readiness_state == "UNKNOWN" or risk_level == "UNKNOWN"
     -> "INSUFFICIENT_DATA". Uncertainty is never resolved into a concrete
     decision; required_information explains exactly what is missing.
  2. readiness_state == "BLOCKED" and risk_level == "CRITICAL"
     -> "IMMEDIATE_ACTION_REQUIRED".
  3. readiness_state == "BLOCKED" (any other risk_level)
     -> "ACTION_REQUIRED".
  4. readiness_state == "READY" and warning_count > 0
     -> "MONITOR" (no hard blocker, but D2-4 has raised at least one
     non-blocking concern -- e.g. a REVIEW_REQUIRED obligation or an open
     non-critical finding -- worth tracking).
  5. Otherwise (readiness_state == "READY", risk_level == "LOW", no
     warnings) -> "NO_ACTION_REQUIRED".
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.schemas.intelligence import AssetDecision, DecisionState
from app.services.intelligence.priority_intelligence_service import (
    get_asset_priority_intelligence,
)


def get_asset_decision(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetDecision:
    priority = get_asset_priority_intelligence(
        db, organization_id=organization_id, asset_id=asset_id
    )

    required_information: list[str] = []
    explanation: list[str] = [
        f"readiness_state={priority.readiness_state!r}, risk_level={priority.risk_level!r}, "
        f"priority_level={priority.priority_level!r}."
    ]

    if priority.readiness_state == "UNKNOWN" or priority.risk_level == "UNKNOWN":
        decision_state: DecisionState = "INSUFFICIENT_DATA"
        decision_reason = (
            "Readiness and/or risk could not be determined from available compliance, "
            "evidence, inspection, or finding data -- a decision cannot be made without "
            "resolving this uncertainty."
        )
        if priority.readiness_state == "UNKNOWN":
            required_information.append(
                "Readiness intelligence is UNKNOWN -- typically caused by zero evaluated "
                "compliance obligations for this asset (see contributing_factors on the "
                "readiness endpoint)."
            )
        if priority.risk_level == "UNKNOWN":
            required_information.append(
                "Risk intelligence is UNKNOWN because the underlying compliance "
                "determination is unresolved."
            )
    elif priority.readiness_state == "BLOCKED" and priority.risk_level == "CRITICAL":
        decision_state = "IMMEDIATE_ACTION_REQUIRED"
        decision_reason = (
            "One or more hard blockers are present and risk is graded CRITICAL "
            "(safety-significant finding combined with a blocked compliance "
            "determination, and/or an active AOG condition)."
        )
    elif priority.readiness_state == "BLOCKED":
        decision_state = "ACTION_REQUIRED"
        decision_reason = (
            f"One or more hard blockers are present (risk_level={priority.risk_level!r}); "
            "the asset cannot be considered ready until they are resolved."
        )
    elif priority.warning_count > 0:
        decision_state = "MONITOR"
        decision_reason = (
            f"No hard blocker is present, but {priority.warning_count} non-blocking "
            "intelligence warning(s) exist and should be tracked."
        )
    else:
        decision_state = "NO_ACTION_REQUIRED"
        decision_reason = "No blockers or warnings are present; readiness is READY and risk is LOW."

    return AssetDecision(
        asset_id=asset_id,
        aircraft_id=priority.aircraft_id,
        decision_state=decision_state,
        decision_reason=decision_reason,
        priority_level=priority.priority_level,
        risk_level=priority.risk_level,
        readiness_state=priority.readiness_state,
        required_information=required_information,
        blockers=priority.blockers,
        warnings=priority.warnings,
        explanation=explanation,
        evaluated_at=datetime.datetime.now(datetime.UTC),
    )
