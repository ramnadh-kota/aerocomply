"""D2.2 Risk Intelligence.

Deterministic, explainable risk grading for an asset, built entirely on top
of app/services/intelligence/readiness_intelligence_service.py -- this
module invents no new facts and runs no additional domain queries; it only
grades the counts and operational_state that readiness intelligence already
computed.

Risk factors (each a Kleene tri-state -- see
app/services/applicability/kleene.py -- never collapsed to a plain bool):
  - safety: TRUE if critical_findings_count > 0, else FALSE. (A count of zero
    is a concrete fact, not missing data, so this factor is never UNKNOWN.)
  - compliance: TRUE if aerospace_intelligence_status is RESTRICTED or
    GROUNDED_INTEL, FALSE if NOMINAL/DEGRADED, UNKNOWN if UNKNOWN_INTEL
    (insufficient data to clear the asset -- must never be treated as
    FALSE/no-risk).
  - operational: TRUE if any open work order is release-BLOCKED, else FALSE.
  - overdue: TRUE if overdue_obligations_count > 0, else FALSE.
  - evidence: TRUE if missing_evidence_count > 0 or rejected_evidence_count
    > 0, else FALSE.
  - aog: TRUE if operational_state == "AOG" (app/services/asset_service.py::
    compute_operational_state), else FALSE.

risk_level derivation (deterministic rule table, evaluated in this order):
  1. is_at_risk = Kleene OR of all six factors above.
     - If is_at_risk is UNKNOWN (no TRUE factor, but at least one UNKNOWN),
       risk_level = "UNKNOWN". A risk assessment is never allowed to default
       to LOW when the underlying compliance state is itself unresolved.
     - If is_at_risk is FALSE (every factor is FALSE), risk_level = "LOW".
  2. Otherwise (is_at_risk is TRUE), grade severity among the TRUE factors:
     - aog TRUE, or (safety TRUE and compliance TRUE) -> "CRITICAL"
       (an aircraft/drone actively AOG, or one with both an unresolved
       critical finding and a BLOCKED compliance determination, is the most
       operationally severe case this rule table recognizes).
     - safety TRUE, or compliance TRUE, or operational TRUE -> "HIGH"
     - otherwise (only overdue and/or evidence factors are TRUE) -> "MEDIUM"
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.schemas.aerospace_state import AerospaceIntelligenceStatus
from app.schemas.intelligence import AssetRiskIntelligence, RiskFactor, RiskLevel
from app.services.applicability.kleene import KleeneValue, kleene_or_all
from app.services.intelligence.readiness_intelligence_service import (
    get_asset_readiness_intelligence,
)


def get_asset_risk_intelligence(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetRiskIntelligence:
    readiness = get_asset_readiness_intelligence(
        db, organization_id=organization_id, asset_id=asset_id
    )
    factors = readiness.contributing_factors

    critical_findings_count = int(factors["critical_findings_count"])
    overdue_obligations_count = int(factors["overdue_obligations_count"])
    missing_evidence_count = int(factors["missing_evidence_count"])
    rejected_evidence_count = int(factors["rejected_evidence_count"])
    blocked_work_orders_count = int(factors["blocked_work_orders_count"])
    aerospace_intelligence_status = str(factors["aerospace_intelligence_status"])
    operational_state = str(factors["operational_state"])

    safety = KleeneValue.TRUE if critical_findings_count > 0 else KleeneValue.FALSE
    if aerospace_intelligence_status in (
        AerospaceIntelligenceStatus.RESTRICTED,
        AerospaceIntelligenceStatus.GROUNDED_INTEL,
    ):
        compliance = KleeneValue.TRUE
    elif aerospace_intelligence_status == AerospaceIntelligenceStatus.UNKNOWN_INTEL:
        compliance = KleeneValue.UNKNOWN
    else:
        compliance = KleeneValue.FALSE
    operational = KleeneValue.TRUE if blocked_work_orders_count > 0 else KleeneValue.FALSE
    overdue = KleeneValue.TRUE if overdue_obligations_count > 0 else KleeneValue.FALSE
    evidence = (
        KleeneValue.TRUE
        if (missing_evidence_count > 0 or rejected_evidence_count > 0)
        else KleeneValue.FALSE
    )
    aog = KleeneValue.TRUE if operational_state == "AOG" else KleeneValue.FALSE

    risk_factors = [
        RiskFactor(
            name="safety",
            value=safety.value,
            explanation=f"{critical_findings_count} unresolved critical finding(s).",
        ),
        RiskFactor(
            name="compliance",
            value=compliance.value,
            explanation=f"Aerospace intelligence status is {aerospace_intelligence_status!r}.",
        ),
        RiskFactor(
            name="operational",
            value=operational.value,
            explanation=f"{blocked_work_orders_count} release-BLOCKED open work order(s).",
        ),
        RiskFactor(
            name="overdue",
            value=overdue.value,
            explanation=f"{overdue_obligations_count} overdue compliance obligation(s).",
        ),
        RiskFactor(
            name="evidence",
            value=evidence.value,
            explanation=(
                f"{missing_evidence_count} missing / {rejected_evidence_count} "
                "rejected evidence item(s)."
            ),
        ),
        RiskFactor(
            name="aog",
            value=aog.value,
            explanation=f"Operational state is {operational_state!r}.",
        ),
    ]

    is_at_risk = kleene_or_all([safety, compliance, operational, overdue, evidence, aog])

    explanation: list[str] = []
    if is_at_risk is KleeneValue.UNKNOWN:
        risk_level: RiskLevel = "UNKNOWN"
        explanation.append(
            "No factor is definitively TRUE, but compliance status is unresolved -- "
            "risk cannot be graded LOW without more data."
        )
    elif is_at_risk is KleeneValue.FALSE:
        risk_level = "LOW"
        explanation.append("Every risk factor is FALSE.")
    else:
        aog_or_safety_and_compliance = aog is KleeneValue.TRUE or (
            safety is KleeneValue.TRUE and compliance is KleeneValue.TRUE
        )
        if aog_or_safety_and_compliance:
            risk_level = "CRITICAL"
            explanation.append(
                "AOG and/or both an unresolved critical finding and a BLOCKED "
                "compliance determination are present."
            )
        elif (
            safety is KleeneValue.TRUE
            or compliance is KleeneValue.TRUE
            or operational is KleeneValue.TRUE
        ):
            risk_level = "HIGH"
            explanation.append(
                "Safety, compliance, or operational readiness is directly impacted."
            )
        else:
            risk_level = "MEDIUM"
            explanation.append("Only overdue obligations and/or evidence gaps are present.")

    return AssetRiskIntelligence(
        asset_id=asset_id,
        risk_level=risk_level,
        readiness_state=readiness.readiness_state,
        factors=risk_factors,
        contributing_counts={
            "critical_findings_count": critical_findings_count,
            "overdue_obligations_count": overdue_obligations_count,
            "missing_evidence_count": missing_evidence_count,
            "rejected_evidence_count": rejected_evidence_count,
            "blocked_work_orders_count": blocked_work_orders_count,
        },
        explanation=explanation,
        evaluated_at=datetime.datetime.now(datetime.UTC),
    )
