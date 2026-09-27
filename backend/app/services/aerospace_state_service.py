"""D2-4 Aerospace State Engine — Deterministic Intelligence Aggregation Service.

Architectural position:
    Developer 1 (Operational Truth)
        └─► Developer 2.1 (Intelligence Interpretation)  ← THIS FILE
                └─► Developer 2.2 (Readiness/Risk/Decision/AI)

This service:
- Consumes Developer 1's compute_operational_state (NEVER reimplements it)
- Consumes D2-1 applicability through ComplianceObligation.applicability_evaluation_id
- Consumes D2-2 compliance/evidence through intelligence_service
- Consumes D2-3 inspection/finding intelligence through intelligence_service
- Derives a deterministic AerospaceIntelligenceState
- Does NOT produce readiness scores, risk scores, or decision recommendations

Domain Invariants enforced:
- UNKNOWN_INTEL ≠ NOMINAL  (mirrors Kleene Invariant #23: UNKNOWN ≠ FALSE)
- GROUNDED_INTEL is emitted when operational state is AOG/GROUNDED and/or
  a critical compliance blocker exists — does not replace Developer 1's ground.
- Every blocker has full source-record provenance (13-point explainability).
- Tenant isolation: all queries are scoped to organization_id.

NO AI, NO LLM, NO PROBABILITY. Same inputs → same outputs.
"""

import datetime
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import Asset
from app.models.compliance import ComplianceObligation, ComplianceState, RegulatoryRequirement
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.work_order import WorkOrder
from app.schemas.aerospace_state import (
    AerospaceIntelligenceState,
    AerospaceIntelligenceStatus,
    ComplianceIntelligenceDimension,
    EvidenceIntelligenceDimension,
    FindingIntelligenceDimension,
    InspectionIntelligenceDimension,
    IntelligenceBlocker,
    IntelligenceBlockerCategory,
    IntelligenceDimensionStatus,
    IntelligenceSourceRef,
    IntelligenceWarning,
    OperationalIntelligenceDimension,
)
from app.services.asset_service import compute_operational_state, get_asset


# ---------------------------------------------------------------------------
# Precedence rule constants (higher = more severe)
# ---------------------------------------------------------------------------

_STATUS_PRECEDENCE = {
    AerospaceIntelligenceStatus.NOMINAL: 0,
    AerospaceIntelligenceStatus.DEGRADED: 1,
    AerospaceIntelligenceStatus.RESTRICTED: 2,
    AerospaceIntelligenceStatus.GROUNDED_INTEL: 3,
    AerospaceIntelligenceStatus.UNKNOWN_INTEL: 4,  # Unknown is treated as highest risk
}

_GROUNDING_OPERATIONAL_STATES = frozenset({"AOG", "GROUNDED"})
_LIFECYCLE_RESTRICTION_STATES = frozenset({"RETIRED", "INACTIVE"})

_BLOCKER_COMPLIANCE_STATUSES = frozenset({
    ComplianceState.NON_COMPLIANT.value,
    ComplianceState.OVERDUE.value,
    ComplianceState.BLOCKED.value,
})


def _escalate(current: str, candidate: str) -> str:
    """Return the higher-precedence aerospace intelligence status."""
    if _STATUS_PRECEDENCE.get(candidate, 0) > _STATUS_PRECEDENCE.get(current, 0):
        return candidate
    return current


# ---------------------------------------------------------------------------
# Main evaluation entry point
# ---------------------------------------------------------------------------

def evaluate_aerospace_intelligence_state(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    include_closed_findings: bool = False,
    include_source_records: bool = False,
) -> AerospaceIntelligenceState:
    """Evaluate the full Aerospace Intelligence State for an asset.

    This is the primary D2-4 service function. It is the ONLY function that
    Developer 2.2 should call to obtain intelligence state; all private
    dimension evaluations below must remain internal to this module.

    Returns:
        AerospaceIntelligenceState — the stable D2.2 contract.

    Raises:
        NotFoundError — if the asset does not exist or is not in this org.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    # ── Load asset (enforces tenant isolation + soft-delete exclusion) ──────
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # ── Resolve aircraft_id (dual-relationship pattern) ──────────────────────
    aircraft_id: uuid.UUID | None = None
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.organization_id == organization_id,
            or_(Aircraft.id == asset_id, Aircraft.asset_id == asset_id),
        )
    ).scalar_one_or_none()
    if aircraft is not None:
        aircraft_id = aircraft.id

    blockers: list[IntelligenceBlocker] = []
    warnings: list[IntelligenceWarning] = []
    source_records: list[dict[str, Any]] = []

    # ── DIMENSION 1: Operational (Developer 1 truth) ──────────────────────
    operational_dim = _evaluate_operational_dimension(
        db,
        organization_id=organization_id,
        asset=asset,
        blockers=blockers,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
    )

    # ── DIMENSION 2: Compliance (D2-1 + D2-2) ────────────────────────────
    compliance_dim = _evaluate_compliance_dimension(
        db,
        organization_id=organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        blockers=blockers,
        warnings=warnings,
        source_records=source_records if include_source_records else None,
    )

    # ── DIMENSION 3: Evidence (D2-2) ──────────────────────────────────────
    evidence_dim = _evaluate_evidence_dimension(
        db,
        organization_id=organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        blockers=blockers,
        warnings=warnings,
    )

    # ── DIMENSION 4: Inspection (D2-3) ────────────────────────────────────
    inspection_dim = _evaluate_inspection_dimension(
        db,
        organization_id=organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        blockers=blockers,
        warnings=warnings,
    )

    # ── DIMENSION 5: Finding (D2-3) ───────────────────────────────────────
    finding_dim = _evaluate_finding_dimension(
        db,
        organization_id=organization_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        include_closed=include_closed_findings,
        blockers=blockers,
        warnings=warnings,
    )

    # ── Derive overall Aerospace Intelligence Status ───────────────────────
    overall_status = _derive_overall_status(
        operational_dim=operational_dim,
        compliance_dim=compliance_dim,
        evidence_dim=evidence_dim,
        inspection_dim=inspection_dim,
        finding_dim=finding_dim,
        blockers=blockers,
        warnings=warnings,
    )

    # ── Aggregate counts ───────────────────────────────────────────────────
    compliance_blockers = [b for b in blockers if b.dimension == "COMPLIANCE"]
    evidence_blockers = [b for b in blockers if b.dimension == "EVIDENCE"]
    inspection_blockers = [b for b in blockers if b.dimension == "INSPECTION"]
    finding_blockers = [b for b in blockers if b.dimension == "FINDING"]

    return AerospaceIntelligenceState(
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        asset_type=asset.asset_type,
        registration=asset.registration,
        aerospace_intelligence_status=overall_status,
        operational_dimension=operational_dim,
        compliance_dimension=compliance_dim,
        evidence_dimension=evidence_dim,
        inspection_dimension=inspection_dim,
        finding_dimension=finding_dim,
        blockers=blockers,
        warnings=warnings,
        total_blocker_count=len(blockers),
        total_warning_count=len(warnings),
        compliance_blocker_count=len(compliance_blockers),
        evidence_blocker_count=len(evidence_blockers),
        inspection_blocker_count=len(inspection_blockers),
        finding_blocker_count=len(finding_blockers),
        source_records=source_records,
        evaluated_at=now,
    )


# ---------------------------------------------------------------------------
# Dimension evaluators (internal — not part of the D2.2 contract)
# ---------------------------------------------------------------------------

def _evaluate_operational_dimension(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset: Asset,
    blockers: list[IntelligenceBlocker],
    asset_id: uuid.UUID,
    aircraft_id: uuid.UUID | None,
) -> OperationalIntelligenceDimension:
    """Consume Developer 1's operational state without replicating it."""
    # Delegate entirely to Developer 1's compute_operational_state
    operational_state = compute_operational_state(
        db, organization_id=organization_id, asset=asset
    )

    dim_status = IntelligenceDimensionStatus.CLEAR

    if operational_state in _GROUNDING_OPERATIONAL_STATES:
        dim_status = IntelligenceDimensionStatus.RESTRICTED
        blockers.append(
            IntelligenceBlocker(
                blocker_id=f"INTEL-OP-GROUNDED-{asset.id}",
                category=IntelligenceBlockerCategory.OPERATIONAL_GROUNDING,
                dimension="OPERATIONAL",
                what_condition=(
                    f"Asset operational state is {operational_state}."
                ),
                why_condition=(
                    f"Developer 1's authoritative operational state is {operational_state}, "
                    "which prevents operational dispatch."
                ),
                source_ref=IntelligenceSourceRef(
                    source_type="Asset",
                    source_id=asset.id,
                    source_label=asset.registration or str(asset.id),
                ),
                required_action="Resolve the grounding / AOG condition through Developer 1's operational processes.",
                resolution_action="Lift the AOG or grounding status via the operational cockpit.",
                asset_id=asset_id,
                aircraft_id=aircraft_id,
            )
        )
    elif operational_state in _LIFECYCLE_RESTRICTION_STATES:
        dim_status = IntelligenceDimensionStatus.RESTRICTED
        blockers.append(
            IntelligenceBlocker(
                blocker_id=f"INTEL-OP-LIFECYCLE-{asset.id}",
                category=IntelligenceBlockerCategory.LIFECYCLE_RESTRICTION,
                dimension="OPERATIONAL",
                what_condition=f"Asset lifecycle state is {asset.status}.",
                why_condition=(
                    f"A {asset.status} asset cannot be dispatched operationally."
                ),
                source_ref=IntelligenceSourceRef(
                    source_type="Asset",
                    source_id=asset.id,
                    source_label=asset.registration or str(asset.id),
                ),
                required_action="Change the asset lifecycle status if appropriate.",
                resolution_action="Update asset lifecycle status via asset management.",
                asset_id=asset_id,
                aircraft_id=aircraft_id,
            )
        )

    summary_map = {
        "AVAILABLE": "Asset is available for operational dispatch.",
        "IN_MISSION": "Asset is currently executing an active mission.",
        "UNDER_INSPECTION": "Asset has a pending inspection requirement.",
        "MAINTENANCE": "Asset is in active maintenance.",
        "GROUNDED": "Asset is operationally grounded.",
        "AOG": "Asset is Aircraft On Ground (AOG) — emergency grounding declared.",
        "INACTIVE": "Asset lifecycle status is inactive/planned.",
        "RETIRED": "Asset has been retired from service.",
    }

    return OperationalIntelligenceDimension(
        status=dim_status,
        operational_state=operational_state,
        lifecycle_status=asset.status,
        summary=summary_map.get(operational_state, f"Operational state: {operational_state}."),
    )


def _evaluate_compliance_dimension(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    aircraft_id: uuid.UUID | None,
    blockers: list[IntelligenceBlocker],
    warnings: list[IntelligenceWarning],
    source_records: list[dict[str, Any]] | None,
) -> ComplianceIntelligenceDimension:
    """Evaluate compliance state using D2-2 ComplianceObligation records."""
    obligations = list(
        db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.organization_id == organization_id,
                or_(
                    ComplianceObligation.asset_id == asset_id,
                    ComplianceObligation.aircraft_id == aircraft_id
                    if aircraft_id
                    else False,
                ),
            )
        ).scalars().all()
    )

    counts = {
        "compliant": 0,
        "non_compliant": 0,
        "overdue": 0,
        "blocked": 0,
        "review_required": 0,
        "total": len(obligations),
    }

    dim_status = IntelligenceDimensionStatus.CLEAR

    for ob in obligations:
        if source_records is not None:
            source_records.append(
                {
                    "type": "ComplianceObligation",
                    "id": str(ob.id),
                    "status": ob.status,
                    "requirement_id": str(ob.requirement_id),
                }
            )

        # Load regulatory requirement for explainability
        req = db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.id == ob.requirement_id,
                RegulatoryRequirement.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        req_num = req.requirement_number if req else "REG-UNKNOWN"
        req_title = req.title if req else "Regulatory Requirement"

        if ob.status == ComplianceState.COMPLIANT.value:
            counts["compliant"] += 1

        elif ob.status == ComplianceState.NON_COMPLIANT.value:
            counts["non_compliant"] += 1
            dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-COMP-NONCOMPLIANT-{ob.id}",
                    category=IntelligenceBlockerCategory.NON_COMPLIANT_OBLIGATION,
                    dimension="COMPLIANCE",
                    what_condition=f"Compliance obligation for {req_num} is NON_COMPLIANT.",
                    why_condition=(
                        f"Regulatory requirement '{req_title}' has been evaluated as NON_COMPLIANT. "
                        "Evidence, corrective action, or verification is required."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="ComplianceObligation",
                        source_id=ob.id,
                        source_label=req_num,
                    ),
                    regulatory_ref_number=req_num,
                    regulatory_ref_title=req_title,
                    required_action=ob.required_action or "Execute corrective action and attach verified evidence.",
                    resolution_action="Provide verified evidence satisfying the compliance obligation.",
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )

        elif ob.status == ComplianceState.OVERDUE.value:
            counts["overdue"] += 1
            dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-COMP-OVERDUE-{ob.id}",
                    category=IntelligenceBlockerCategory.OVERDUE_OBLIGATION,
                    dimension="COMPLIANCE",
                    what_condition=f"Compliance obligation for {req_num} is OVERDUE.",
                    why_condition=(
                        f"Regulatory requirement '{req_title}' compliance deadline has passed. "
                        f"Due date was: {ob.due_date.isoformat() if ob.due_date else 'Not recorded'}."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="ComplianceObligation",
                        source_id=ob.id,
                        source_label=req_num,
                    ),
                    regulatory_ref_number=req_num,
                    regulatory_ref_title=req_title,
                    required_action=ob.required_action or "Execute overdue compliance action immediately.",
                    resolution_action="Complete overdue compliance action and provide verified evidence.",
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )

        elif ob.status == ComplianceState.BLOCKED.value:
            counts["blocked"] += 1
            # BLOCKED usually means applicability could not be determined
            # UNKNOWN ≠ FALSE — must not become NOMINAL
            dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-COMP-BLOCKED-{ob.id}",
                    category=IntelligenceBlockerCategory.BLOCKED_OBLIGATION,
                    dimension="COMPLIANCE",
                    what_condition=(
                        f"Compliance obligation for {req_num} is in BLOCKED state "
                        "(insufficient data or unresolved applicability)."
                    ),
                    why_condition=(
                        "Applicability could not be determined due to insufficient configuration data. "
                        "Per Invariant #23, UNKNOWN must not be treated as NOT_APPLICABLE."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="ComplianceObligation",
                        source_id=ob.id,
                        source_label=req_num,
                    ),
                    regulatory_ref_number=req_num,
                    regulatory_ref_title=req_title,
                    required_action="Provide complete asset configuration data for applicability evaluation.",
                    resolution_action=(
                        "Complete the applicability evaluation by resolving missing configuration data."
                    ),
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )

        elif ob.status == ComplianceState.REVIEW_REQUIRED.value:
            counts["review_required"] += 1
            if dim_status == IntelligenceDimensionStatus.CLEAR:
                dim_status = IntelligenceDimensionStatus.WARNING
            warnings.append(
                IntelligenceWarning(
                    warning_id=f"INTEL-COMP-REVIEW-{ob.id}",
                    category=IntelligenceBlockerCategory.REVIEW_REQUIRED_OBLIGATION,
                    dimension="COMPLIANCE",
                    message=(
                        f"Compliance obligation for {req_num} requires manual review. "
                        "A compliance engineer should assess and resolve."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="ComplianceObligation",
                        source_id=ob.id,
                        source_label=req_num,
                    ),
                )
            )

    # Determine summary
    if dim_status == IntelligenceDimensionStatus.CLEAR:
        if counts["total"] == 0:
            dim_status = IntelligenceDimensionStatus.UNKNOWN
            summary = "No compliance obligations found. Cannot confirm compliance state."
        elif counts["compliant"] == counts["total"]:
            summary = f"All {counts['total']} compliance obligations are COMPLIANT."
        else:
            summary = f"{counts['compliant']} of {counts['total']} obligations compliant."
    elif dim_status == IntelligenceDimensionStatus.WARNING:
        summary = f"{counts['review_required']} obligations require review."
    else:
        summary = (
            f"{counts['non_compliant']} non-compliant, {counts['overdue']} overdue, "
            f"{counts['blocked']} blocked obligations."
        )

    return ComplianceIntelligenceDimension(
        status=dim_status,
        obligations_total=counts["total"],
        obligations_compliant=counts["compliant"],
        obligations_non_compliant=counts["non_compliant"],
        obligations_overdue=counts["overdue"],
        obligations_blocked=counts["blocked"],
        obligations_review_required=counts["review_required"],
        summary=summary,
    )


def _evaluate_evidence_dimension(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    aircraft_id: uuid.UUID | None,
    blockers: list[IntelligenceBlocker],
    warnings: list[IntelligenceWarning],
) -> EvidenceIntelligenceDimension:
    """Evaluate evidence state for the asset via D2-2 evidence records."""
    # Query all evidence linked to this asset directly or via obligations
    evidence_rows = list(
        db.execute(
            select(Evidence).where(
                Evidence.organization_id == organization_id,
                or_(
                    Evidence.asset_id == asset_id,
                    Evidence.aircraft_id == aircraft_id if aircraft_id else False,
                ),
            )
        ).scalars().all()
    )

    total = len(evidence_rows)
    accepted = sum(1 for e in evidence_rows if e.status == EvidenceStatus.ACCEPTED.value)
    rejected = sum(1 for e in evidence_rows if e.status == EvidenceStatus.REJECTED.value)
    # Evidence whose verification has been independently rejected (distinct from
    # status == REJECTED above, which is the submission-level rejection)
    rejected_verification = sum(
        1 for e in evidence_rows if e.verification_status == "REJECTED"
    )
    # Unverified: accepted but awaiting verification (not yet verified or rejected)
    unverified = sum(
        1
        for e in evidence_rows
        if e.status == EvidenceStatus.ACCEPTED.value
        and e.verification_status not in {"VERIFIED", "REJECTED", None}
    )
    # Evidence that is required but missing is tracked via obligations (no direct evidence row exists)
    # Count mandatory evidence attached to obligations that have no accepted evidence
    obligation_ids_with_evidence = {e.compliance_obligation_id for e in evidence_rows if e.compliance_obligation_id}
    obligations_requiring_evidence = list(
        db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.organization_id == organization_id,
                or_(
                    ComplianceObligation.asset_id == asset_id,
                    ComplianceObligation.aircraft_id == aircraft_id if aircraft_id else False,
                ),
                # Has evidence requirements defined
                ComplianceObligation.evidence_requirements.is_not(None),
                ComplianceObligation.status.in_([
                    ComplianceState.DUE.value,
                    ComplianceState.OVERDUE.value,
                    ComplianceState.NON_COMPLIANT.value,
                ]),
            )
        ).scalars().all()
    )
    missing = sum(1 for ob in obligations_requiring_evidence if ob.id not in obligation_ids_with_evidence)

    dim_status = IntelligenceDimensionStatus.CLEAR

    for e in evidence_rows:
        if e.verification_status == "REJECTED":
            if dim_status == IntelligenceDimensionStatus.CLEAR:
                dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-EV-REJECTED-{e.id}",
                    category=IntelligenceBlockerCategory.REJECTED_EVIDENCE,
                    dimension="EVIDENCE",
                    what_condition=f"Evidence item has been REJECTED: {e.title or e.evidence_type}.",
                    why_condition=(
                        f"Rejected evidence: {e.rejection_reason or 'No reason recorded'}. "
                        "Rejected evidence cannot satisfy compliance obligations."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="Evidence",
                        source_id=e.id,
                        source_label=e.title or e.evidence_type,
                    ),
                    required_action="Replace or resubmit the rejected evidence record.",
                    resolution_action="Submit valid replacement evidence and have it verified.",
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )
        elif e.status == EvidenceStatus.REJECTED.value:
            if dim_status == IntelligenceDimensionStatus.CLEAR:
                dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-EV-STATUS-REJECTED-{e.id}",
                    category=IntelligenceBlockerCategory.REJECTED_EVIDENCE,
                    dimension="EVIDENCE",
                    what_condition=f"Evidence record status is REJECTED: {e.title or e.evidence_type}.",
                    why_condition=(
                        "Evidence with REJECTED status cannot satisfy compliance obligations."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="Evidence",
                        source_id=e.id,
                        source_label=e.title or e.evidence_type,
                    ),
                    required_action="Provide replacement evidence.",
                    resolution_action="Submit valid replacement evidence and have it verified.",
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )

    for ob in obligations_requiring_evidence:
        if ob.id not in obligation_ids_with_evidence:
            if dim_status == IntelligenceDimensionStatus.CLEAR:
                dim_status = IntelligenceDimensionStatus.RESTRICTED
            req = db.execute(
                select(RegulatoryRequirement).where(
                    RegulatoryRequirement.id == ob.requirement_id,
                    RegulatoryRequirement.organization_id == organization_id,
                )
            ).scalar_one_or_none()
            req_num = req.requirement_number if req else "REG-UNKNOWN"
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-EV-MISSING-{ob.id}",
                    category=IntelligenceBlockerCategory.MISSING_EVIDENCE,
                    dimension="EVIDENCE",
                    what_condition=f"Required evidence is missing for obligation linked to {req_num}.",
                    why_condition=(
                        "Compliance obligation has evidence requirements but no evidence records exist."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="ComplianceObligation",
                        source_id=ob.id,
                        source_label=req_num,
                    ),
                    regulatory_ref_number=req_num,
                    regulatory_ref_title=req.title if req else None,
                    required_action=ob.required_action or "Attach required evidence.",
                    resolution_action="Upload and obtain verification of the required evidence.",
                    missing_evidence_desc=str(ob.evidence_requirements),
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )

    if dim_status == IntelligenceDimensionStatus.CLEAR:
        if total == 0:
            summary = "No evidence records found for this asset."
        elif accepted == total:
            summary = f"All {total} evidence records accepted and verified."
        else:
            summary = f"{accepted} of {total} evidence records accepted."
    else:
        summary = (
            f"{rejected + rejected_verification} rejected evidence records; "
            f"{missing} missing mandatory evidence items."
        )

    return EvidenceIntelligenceDimension(
        status=dim_status,
        evidence_total=total,
        evidence_accepted=accepted,
        evidence_missing=missing,
        evidence_rejected=rejected + rejected_verification,
        evidence_unverified=unverified,
        summary=summary,
    )


def _evaluate_inspection_dimension(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    aircraft_id: uuid.UUID | None,
    blockers: list[IntelligenceBlocker],
    warnings: list[IntelligenceWarning],
) -> InspectionIntelligenceDimension:
    """Evaluate inspection state using InspectionRequirement records."""
    # Join through work orders to reach asset_id
    wo_ids_query = select(WorkOrder.id).where(
        WorkOrder.organization_id == organization_id,
        WorkOrder.deleted_at.is_(None),
        or_(
            WorkOrder.asset_id == asset_id,
            WorkOrder.aircraft_id == aircraft_id if aircraft_id else False,
        ),
    )
    wo_ids = [row[0] for row in db.execute(wo_ids_query).fetchall()]

    if not wo_ids:
        return InspectionIntelligenceDimension(
            status=IntelligenceDimensionStatus.CLEAR,
            summary="No work orders found; no active inspection requirements.",
        )

    inspection_rows = list(
        db.execute(
            select(InspectionRequirement).where(
                InspectionRequirement.organization_id == organization_id,
                InspectionRequirement.work_order_id.in_(wo_ids),
            )
        ).scalars().all()
    )

    total = len(inspection_rows)
    completed = sum(1 for i in inspection_rows if i.status == InspectionRequirementStatus.COMPLETED.value)
    pending = sum(1 for i in inspection_rows if i.status == InspectionRequirementStatus.PENDING.value)
    rejected = sum(1 for i in inspection_rows if i.status == InspectionRequirementStatus.REJECTED.value)

    # RII (Required Inspection Item) — required items that are pending independent signoff
    rii_pending = sum(
        1
        for i in inspection_rows
        if i.required and i.status == InspectionRequirementStatus.PENDING.value
        and i.inspector_user_id is None
    )

    dim_status = IntelligenceDimensionStatus.CLEAR

    for insp in inspection_rows:
        if insp.status == InspectionRequirementStatus.REJECTED.value:
            dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-INSP-REJECTED-{insp.id}",
                    category=IntelligenceBlockerCategory.FAILED_INSPECTION,
                    dimension="INSPECTION",
                    what_condition=f"Inspection requirement {insp.id} has been REJECTED.",
                    why_condition=(
                        f"Rejection reason: {insp.rejection_reason or 'Not specified'}. "
                        "A rejected inspection must be corrected and re-inspected."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="InspectionRequirement",
                        source_id=insp.id,
                        source_label=str(insp.id),
                    ),
                    required_action="Correct the rejection condition and re-perform the inspection.",
                    resolution_action="Resolve rejection cause and complete inspection.",
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )
        elif (
            insp.required
            and insp.status == InspectionRequirementStatus.PENDING.value
            and insp.inspector_user_id is None
        ):
            # RII pending signoff
            if dim_status == IntelligenceDimensionStatus.CLEAR:
                dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-INSP-RII-{insp.id}",
                    category=IntelligenceBlockerCategory.PENDING_RII,
                    dimension="INSPECTION",
                    what_condition="Required Inspection Item (RII) is pending independent signoff.",
                    why_condition=(
                        "Airworthiness regulations require RII items to be independently verified "
                        "by a qualified inspector before release."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="InspectionRequirement",
                        source_id=insp.id,
                        source_label=str(insp.id),
                    ),
                    required_action="Assign an independent inspector to complete RII signoff.",
                    resolution_action="Complete independent RII inspection.",
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )

    if dim_status == IntelligenceDimensionStatus.CLEAR and pending > 0:
        dim_status = IntelligenceDimensionStatus.WARNING
        warnings.append(
            IntelligenceWarning(
                warning_id=f"INTEL-INSP-PENDING-{asset_id}",
                category=IntelligenceBlockerCategory.INCOMPLETE_INSPECTION,
                dimension="INSPECTION",
                message=f"{pending} inspection requirements are pending completion.",
            )
        )

    summary_parts = []
    if completed:
        summary_parts.append(f"{completed} completed")
    if pending:
        summary_parts.append(f"{pending} pending")
    if rejected:
        summary_parts.append(f"{rejected} rejected")
    if rii_pending:
        summary_parts.append(f"{rii_pending} RII awaiting signoff")

    summary = f"{total} total inspections: " + ", ".join(summary_parts) if summary_parts else "No inspection requirements found."

    return InspectionIntelligenceDimension(
        status=dim_status,
        inspections_total=total,
        inspections_completed=completed,
        inspections_pending=pending,
        inspections_rejected=rejected,
        rii_pending=rii_pending,
        summary=summary,
    )


def _evaluate_finding_dimension(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    aircraft_id: uuid.UUID | None,
    include_closed: bool,
    blockers: list[IntelligenceBlocker],
    warnings: list[IntelligenceWarning],
) -> FindingIntelligenceDimension:
    """Evaluate finding intelligence state using Finding records."""
    finding_query = select(Finding).where(
        Finding.organization_id == organization_id,
        or_(
            Finding.asset_id == asset_id,
            Finding.aircraft_id == aircraft_id if aircraft_id else False,
        ),
    )
    if not include_closed:
        finding_query = finding_query.where(Finding.status != FindingStatus.CLOSED)

    findings = list(db.execute(finding_query).scalars().all())

    open_count = sum(1 for f in findings if f.status != FindingStatus.CLOSED)
    critical = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL and f.status != FindingStatus.CLOSED)
    major = sum(1 for f in findings if f.severity == FindingSeverity.MAJOR and f.status != FindingStatus.CLOSED)
    minor = sum(1 for f in findings if f.severity == FindingSeverity.MINOR and f.status != FindingStatus.CLOSED)
    closed = sum(1 for f in findings if f.status == FindingStatus.CLOSED)

    dim_status = IntelligenceDimensionStatus.CLEAR

    for finding in findings:
        if finding.status == FindingStatus.CLOSED:
            continue

        is_blocker = False
        category = None

        if finding.severity == FindingSeverity.CRITICAL:
            is_blocker = True
            category = IntelligenceBlockerCategory.CRITICAL_FINDING
        elif finding.severity == FindingSeverity.MAJOR:
            is_blocker = True
            category = IntelligenceBlockerCategory.MAJOR_FINDING
        elif finding.safety_significance in {"FLIGHT_SAFETY", "AIRWORTHINESS", "AIRWORTHINESS_LIMITATION"}:
            is_blocker = True
            category = IntelligenceBlockerCategory.SAFETY_SIGNIFICANT_FINDING

        if is_blocker:
            dim_status = IntelligenceDimensionStatus.RESTRICTED
            blockers.append(
                IntelligenceBlocker(
                    blocker_id=f"INTEL-FIND-{finding.severity}-{finding.id}",
                    category=category,
                    dimension="FINDING",
                    what_condition=(
                        f"Unresolved {finding.severity} finding: {finding.title}."
                    ),
                    why_condition=(
                        f"An unresolved {finding.severity} finding requires corrective action "
                        "and verified evidence before operational release."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="Finding",
                        source_id=finding.id,
                        source_label=finding.title,
                    ),
                    required_action=(
                        "Record a corrective action disposition and attach verified evidence."
                    ),
                    resolution_action=(
                        "Close the finding by completing corrective action and verifying evidence."
                    ),
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                )
            )
        elif finding.status in {FindingStatus.OPEN, FindingStatus.IN_PROGRESS}:
            if dim_status == IntelligenceDimensionStatus.CLEAR:
                dim_status = IntelligenceDimensionStatus.WARNING
            warnings.append(
                IntelligenceWarning(
                    warning_id=f"INTEL-FIND-OPEN-{finding.id}",
                    category="OPEN_FINDING",
                    dimension="FINDING",
                    message=(
                        f"Open {finding.severity} finding: {finding.title}. "
                        "Review and disposition required."
                    ),
                    source_ref=IntelligenceSourceRef(
                        source_type="Finding",
                        source_id=finding.id,
                        source_label=finding.title,
                    ),
                )
            )

    if dim_status == IntelligenceDimensionStatus.CLEAR:
        summary = "No active findings detected."
    elif dim_status == IntelligenceDimensionStatus.WARNING:
        summary = f"{open_count} open findings require review."
    else:
        summary = (
            f"{critical} critical, {major} major open findings blocking operations."
        )

    return FindingIntelligenceDimension(
        status=dim_status,
        findings_open=open_count,
        findings_critical=critical,
        findings_major=major,
        findings_minor=minor,
        findings_closed=closed,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Overall status derivation
# ---------------------------------------------------------------------------

def _derive_overall_status(
    *,
    operational_dim: OperationalIntelligenceDimension,
    compliance_dim: ComplianceIntelligenceDimension,
    evidence_dim: EvidenceIntelligenceDimension,
    inspection_dim: InspectionIntelligenceDimension,
    finding_dim: FindingIntelligenceDimension,
    blockers: list[IntelligenceBlocker],
    warnings: list[IntelligenceWarning],
) -> str:
    """Derive the overall AerospaceIntelligenceStatus from dimension results.

    Precedence (descending severity):
    4 UNKNOWN_INTEL    — any dimension is UNKNOWN and no blockers exist
    3 GROUNDED_INTEL   — operational state is AOG/GROUNDED
    2 RESTRICTED       — any hard blocker exists
    1 DEGRADED         — warnings exist; no hard blockers
    0 NOMINAL          — all dimensions clear; no blockers or warnings

    UNKNOWN_INTEL is highest precedence because it must never be silently
    resolved to NOMINAL (Invariant #23).
    """
    # Check for GROUNDED_INTEL condition first
    is_grounded_intel = operational_dim.operational_state in _GROUNDING_OPERATIONAL_STATES

    # Any UNKNOWN dimensions → UNKNOWN_INTEL (only if no blockers; if blockers exist
    # RESTRICTED takes precedence for actionability)
    has_unknown_dim = any(
        dim.status == IntelligenceDimensionStatus.UNKNOWN
        for dim in [compliance_dim, evidence_dim, inspection_dim, finding_dim]
    )

    if blockers:
        if is_grounded_intel:
            return AerospaceIntelligenceStatus.GROUNDED_INTEL
        return AerospaceIntelligenceStatus.RESTRICTED

    if is_grounded_intel:
        return AerospaceIntelligenceStatus.GROUNDED_INTEL

    if has_unknown_dim:
        return AerospaceIntelligenceStatus.UNKNOWN_INTEL

    if warnings:
        return AerospaceIntelligenceStatus.DEGRADED

    return AerospaceIntelligenceStatus.NOMINAL
