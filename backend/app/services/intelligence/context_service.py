"""M4.5 -- Intelligence Context Contract builder.

IntelligenceContext is a read-only projection of deterministic aerospace
intelligence. It does not create, override, or reinterpret aerospace truth.

This module runs zero new domain queries and implements zero new
intelligence rules. It composes six existing read-only calls:
  - evaluate_aerospace_intelligence_state (D2.1/D2-4) -- for the full-detail
    aerospace_state section (the only source that still carries
    blocker_id/what_condition; see app/schemas/intelligence.py's module
    docstring for why D2.2's own flattened blockers cannot supply this).
  - get_asset_readiness_intelligence, get_asset_risk_intelligence,
    get_asset_priority_intelligence, get_asset_decision,
    get_asset_recommendation (D2.2 Pass 1-3) -- unchanged, verbatim output.

Architectural boundary this contract exists to enforce (M4.5, Section 7):
the future AI Assistant (M5) consumes IntelligenceContext to explain,
summarize, answer, and navigate -- it must never determine compliance,
applicability, airworthiness, readiness, risk, priority, decision, or
recommendation itself, and it can't: every one of those fields already
arrives pre-computed and read-only in this contract, with no field or
method through which a caller could write back into it.
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.schemas.intelligence import (
    IntelligenceAerospaceStateContext,
    IntelligenceAssetContext,
    IntelligenceContext,
    IntelligenceDecisionContext,
    IntelligencePriorityContext,
    IntelligenceReadinessContext,
    IntelligenceRecommendationContext,
    IntelligenceRiskContext,
    IntelligenceTenantContext,
)
from app.services.aerospace_state_service import evaluate_aerospace_intelligence_state
from app.services.intelligence.decision_service import get_asset_decision
from app.services.intelligence.priority_intelligence_service import (
    get_asset_priority_intelligence,
)
from app.services.intelligence.readiness_intelligence_service import (
    get_asset_readiness_intelligence,
)
from app.services.intelligence.recommendation_service import get_asset_recommendation
from app.services.intelligence.risk_intelligence_service import get_asset_risk_intelligence

_CONTRACT_VERSION = "1.0"


def get_asset_intelligence_context(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> IntelligenceContext:
    state = evaluate_aerospace_intelligence_state(
        db, organization_id=organization_id, asset_id=asset_id
    )
    readiness = get_asset_readiness_intelligence(
        db, organization_id=organization_id, asset_id=asset_id
    )
    risk = get_asset_risk_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    priority = get_asset_priority_intelligence(
        db, organization_id=organization_id, asset_id=asset_id
    )
    decision = get_asset_decision(db, organization_id=organization_id, asset_id=asset_id)
    recommendation = get_asset_recommendation(
        db, organization_id=organization_id, asset_id=asset_id
    )

    uncertainty: list[str] = []
    if state.aerospace_intelligence_status == "UNKNOWN_INTEL":
        uncertainty.append(
            "Aerospace Intelligence State is UNKNOWN_INTEL -- at least one dimension "
            "could not be determined from available data."
        )
    if readiness.readiness_state == "UNKNOWN":
        uncertainty.append(
            "Readiness state is UNKNOWN -- insufficient data to confirm this asset is ready."
        )
    if risk.risk_level == "UNKNOWN":
        uncertainty.append(
            "Risk level is UNKNOWN -- the underlying compliance/readiness determination "
            "is unresolved."
        )
    if decision.decision_state == "INSUFFICIENT_DATA":
        uncertainty.extend(decision.required_information)

    return IntelligenceContext(
        contract_version=_CONTRACT_VERSION,
        generated_at=datetime.datetime.now(datetime.UTC),
        tenant=IntelligenceTenantContext(organization_id=organization_id),
        asset=IntelligenceAssetContext(
            asset_id=asset_id,
            aircraft_id=state.aircraft_id,
            asset_type=state.asset_type,
            registration=state.registration,
            operational_state=state.operational_dimension.operational_state,
        ),
        aerospace_state=IntelligenceAerospaceStateContext(
            status=state.aerospace_intelligence_status,
            blockers=state.blockers,
            warnings=state.warnings,
            evaluation_version=state.evaluation_version,
            disclaimer=state.disclaimer,
        ),
        readiness=IntelligenceReadinessContext(
            state=readiness.readiness_state,
            blockers=readiness.blockers,
            data_completeness=readiness.data_completeness,
        ),
        risk=IntelligenceRiskContext(level=risk.risk_level, factors=risk.factors),
        priority=IntelligencePriorityContext(
            level=priority.priority_level,
            escalated=priority.escalated,
            rationale=priority.explanation,
        ),
        decision=IntelligenceDecisionContext(
            state=decision.decision_state,
            rationale=decision.decision_reason,
            required_information=decision.required_information,
        ),
        recommendation=IntelligenceRecommendationContext(
            state=recommendation.recommendation_state,
            items=recommendation.items,
        ),
        uncertainty=uncertainty,
    )
