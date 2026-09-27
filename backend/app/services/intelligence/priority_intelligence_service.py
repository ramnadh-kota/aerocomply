"""D2.2 Pass 2 -- Priority Intelligence.

Consumes -- never re-derives -- app/services/intelligence/
readiness_intelligence_service.py and risk_intelligence_service.py (Pass 1),
plus the D2-4 Aerospace Intelligence State contract
(app/services/aerospace_state_service.py), read directly only for its
`warnings` list, which neither Pass-1 service surfaces. No new domain
queries are run here; every input is either a Pass-1 service's own output
or a read-only passthrough of D2-4's own warnings.

The repository has no pre-existing priority enum to build on (WorkOrder,
PartRequirement, and ComplianceObligation all store `priority` as a
free-form string with inconsistent defaults -- "NORMAL" vs "MEDIUM", no
`ALL_*_PRIORITIES` vocabulary). The only real precedent inside this
architecture is D2.2's own Pass-1 risk tier vocabulary
(CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN), so priority reuses it exactly
(`PriorityLevel = RiskLevel` in app/schemas/intelligence.py) rather than
inventing a second, competing scale.

priority_level derivation (deterministic rule table):
  1. Base priority_level = risk_level, unchanged (CRITICAL/HIGH/MEDIUM/LOW
     pass through as-is; UNKNOWN passes through as UNKNOWN -- never
     resolved to a concrete tier, never treated as "low priority").
  2. One escalation rule, applied only when risk_level is LOW, MEDIUM, or
     HIGH (never applied to UNKNOWN, which must never be reinterpreted
     into a concrete tier): if 3 or more concrete blockers are present
     (readiness_intelligence's unified blocker list, across any source
     domain), escalate one tier (LOW->MEDIUM, MEDIUM->HIGH, HIGH->CRITICAL).
     Rationale: risk_intelligence_service's six factors are each a single
     Kleene TRUE/FALSE/UNKNOWN value -- one unresolved critical finding
     reads identically to five, so risk_level alone cannot distinguish a
     single isolated blocker from several concurrent ones. Blocker *count*
     (not source-domain diversity -- diversity is recorded on the result
     for explainability but is not itself the trigger, since a single
     compliance obligation already drives the overall aerospace state to
     RESTRICTED and therefore the `compliance` risk factor to TRUE, making
     domain-count alone an unreliable escalation signal here) is the one
     additional signal genuinely available and not already reflected in
     risk_level.
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.schemas.intelligence import (
    AssetPriorityIntelligence,
    IntelligenceWarningRef,
    PriorityLevel,
)
from app.services.aerospace_state_service import evaluate_aerospace_intelligence_state
from app.services.intelligence.readiness_intelligence_service import (
    get_asset_readiness_intelligence,
)
from app.services.intelligence.risk_intelligence_service import get_asset_risk_intelligence

_ESCALATION_ELIGIBLE = {"LOW", "MEDIUM", "HIGH"}
_ESCALATION_TARGET = {"LOW": "MEDIUM", "MEDIUM": "HIGH", "HIGH": "CRITICAL"}
_ESCALATION_BLOCKER_THRESHOLD = 3


def get_asset_priority_intelligence(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetPriorityIntelligence:
    readiness = get_asset_readiness_intelligence(
        db, organization_id=organization_id, asset_id=asset_id
    )
    risk = get_asset_risk_intelligence(db, organization_id=organization_id, asset_id=asset_id)
    state = evaluate_aerospace_intelligence_state(
        db, organization_id=organization_id, asset_id=asset_id
    )

    distinct_blocker_domains = len({b.source_domain for b in readiness.blockers})

    warnings = [
        IntelligenceWarningRef(
            warning_id=w.warning_id,
            category=w.category,
            dimension=w.dimension,
            message=w.message,
            source_type=w.source_ref.source_type if w.source_ref else None,
            source_id=w.source_ref.source_id if w.source_ref else None,
            source_label=w.source_ref.source_label if w.source_ref else None,
        )
        for w in state.warnings
    ]

    priority_level: PriorityLevel = risk.risk_level
    escalated = False
    explanation: list[str] = [f"Base priority is risk_level={risk.risk_level!r}."]

    if (
        risk.risk_level in _ESCALATION_ELIGIBLE
        and len(readiness.blockers) >= _ESCALATION_BLOCKER_THRESHOLD
    ):
        priority_level = _ESCALATION_TARGET[risk.risk_level]  # type: ignore[assignment]
        escalated = True
        explanation.append(
            f"Escalated from {risk.risk_level!r} to {priority_level!r}: "
            f"{len(readiness.blockers)} concrete blockers are present, more than "
            "risk_level's binary factors alone distinguish."
        )

    return AssetPriorityIntelligence(
        asset_id=asset_id,
        aircraft_id=state.aircraft_id,
        priority_level=priority_level,
        risk_level=risk.risk_level,
        readiness_state=readiness.readiness_state,
        escalated=escalated,
        blocker_count=len(readiness.blockers),
        distinct_blocker_domains=distinct_blocker_domains,
        warning_count=len(warnings),
        blockers=readiness.blockers,
        warnings=warnings,
        explanation=explanation,
        evaluated_at=datetime.datetime.now(datetime.UTC),
    )
