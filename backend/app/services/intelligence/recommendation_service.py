"""D2.2 Pass 3 -- Recommendation Engine.

Consumes -- never re-derives -- app/services/intelligence/decision_service.py
(which itself consumes priority, which consumes risk and readiness). This
module runs no domain queries of its own and adds no new intelligence
signal; it only classifies AssetDecision's own output into deterministic,
advisory next-step items.

This is the final deterministic stage before human action / future AI
explanation (see architecture chain in this module's own docstring below).
It is NOT an autonomous action engine: it never executes maintenance,
creates or closes a work order, changes aircraft/compliance/evidence/
readiness/operational state, approves release, or calls an LLM. Every
`action` and `resolution_condition` text is either copied verbatim from an
authoritative source field or is one of a small, fixed set of literal
strings for the two branches (INSUFFICIENT_DATA, NO_ACTION_REQUIRED) that
have no source blocker/warning to quote -- nothing is invented.

recommendation_state is DecisionState, reused unchanged (not a fourth
competing vocabulary): recommendation answers "what deterministic next-step
items follow," decision already answered "what state are we in."

Item generation rule table (deterministic, evaluated on decision_state):
  1. decision_state == "INSUFFICIENT_DATA":
     one RecommendationItem per decision.required_information entry,
     action_category="OBTAIN_MISSING_INFORMATION", action=that string
     verbatim, no source_blocker (there are none in this branch --
     decision_service checks readiness/risk UNKNOWN before ever looking at
     blockers).
  2. decision_state in ("IMMEDIATE_ACTION_REQUIRED", "ACTION_REQUIRED"):
     one RecommendationItem per blocker in decision.blockers -- ALL of
     them, never a subset, ordered by source_domain priority
     (AEROSPACE_STATE first, since it is D2.1's most authoritative
     determination; then WORK_ORDER; then DEPLOYMENT), ties broken by
     original (stable) order:
       - if blocker.required_action is set (AEROSPACE_STATE blockers only,
         see readiness_intelligence_service.py), action_category=
         "PERFORM_REQUIRED_ACTION", action=blocker.required_action verbatim,
         resolution_condition=blocker.resolution_action verbatim.
       - otherwise (WORK_ORDER/DEPLOYMENT blockers, which carry no
         authoritative action field in their own source schema),
         action_category="RESOLVE_BLOCKER", action=blocker.description
         verbatim, resolution_condition=None (no authoritative condition
         exists to quote).
  3. decision_state == "MONITOR": one RecommendationItem per warning in
     decision.warnings, action_category="MONITOR_CONDITION",
     action=warning.message verbatim, no source_blocker (warnings are not
     blockers).
  4. decision_state == "NO_ACTION_REQUIRED": a single RecommendationItem,
     action_category="NO_ACTION_REQUIRED", action="No action required.".

Blocker/warning source_domain priority used in rule 2:
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.schemas.intelligence import AssetRecommendation, RecommendationItem
from app.services.intelligence.decision_service import get_asset_decision

_BLOCKER_DOMAIN_PRIORITY = {"AEROSPACE_STATE": 0, "WORK_ORDER": 1, "DEPLOYMENT": 2}


def get_asset_recommendation(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetRecommendation:
    decision = get_asset_decision(db, organization_id=organization_id, asset_id=asset_id)

    items: list[RecommendationItem] = []
    explanation: list[str] = [f"Derived from decision_state={decision.decision_state!r}."]

    if decision.decision_state == "INSUFFICIENT_DATA":
        for info in decision.required_information:
            items.append(
                RecommendationItem(
                    action_category="OBTAIN_MISSING_INFORMATION",
                    action=info,
                    resolution_condition=None,
                    source_blocker=None,
                )
            )
    elif decision.decision_state in ("IMMEDIATE_ACTION_REQUIRED", "ACTION_REQUIRED"):
        ordered_blockers = sorted(
            decision.blockers,
            key=lambda b: _BLOCKER_DOMAIN_PRIORITY.get(b.source_domain, 99),
        )
        explanation.append(
            f"{len(ordered_blockers)} blocker(s) preserved, ordered AEROSPACE_STATE -> "
            "WORK_ORDER -> DEPLOYMENT (D2.1's own determination takes precedence)."
        )
        for blocker in ordered_blockers:
            if blocker.required_action:
                items.append(
                    RecommendationItem(
                        action_category="PERFORM_REQUIRED_ACTION",
                        action=blocker.required_action,
                        resolution_condition=blocker.resolution_action,
                        source_blocker=blocker,
                    )
                )
            else:
                items.append(
                    RecommendationItem(
                        action_category="RESOLVE_BLOCKER",
                        action=blocker.description,
                        resolution_condition=None,
                        source_blocker=blocker,
                    )
                )
    elif decision.decision_state == "MONITOR":
        for warning in decision.warnings:
            items.append(
                RecommendationItem(
                    action_category="MONITOR_CONDITION",
                    action=warning.message,
                    resolution_condition=None,
                    source_blocker=None,
                )
            )
    else:  # NO_ACTION_REQUIRED
        items.append(
            RecommendationItem(
                action_category="NO_ACTION_REQUIRED",
                action="No action required.",
                resolution_condition=None,
                source_blocker=None,
            )
        )

    return AssetRecommendation(
        asset_id=asset_id,
        aircraft_id=decision.aircraft_id,
        recommendation_state=decision.decision_state,
        priority_level=decision.priority_level,
        risk_level=decision.risk_level,
        readiness_state=decision.readiness_state,
        items=items,
        required_information=decision.required_information,
        blockers=decision.blockers,
        warnings=decision.warnings,
        explanation=explanation,
        evaluated_at=datetime.datetime.now(datetime.UTC),
    )
