"""Compliance Intelligence Service.

Connects inspections, findings, maintenance, evidence, and compliance obligations
into a deterministic, auditable digital thread and exposes authoritative compliance
readiness contributions for operational readiness gates.

Domain Invariants Enforced:
- UNKNOWN != FALSE (Invariant #23): missing data yields BLOCKED/UNKNOWN, never NOT_APPLICABLE.
- Unverified or rejected evidence never yields COMPLIANT.
- Every blocker is explainable with source record provenance.
- Clean separation: provides authoritative compliance intelligence inputs to Developer 1's readiness gates.
"""

import datetime
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import Asset
from app.models.compliance import (
    ComplianceObligation,
    ComplianceState,
    RegulatoryRequirement,
)
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.inspection_requirement import (
    InspectionRequirement,
    InspectionRequirementStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.compliance_intelligence import (
    AssetComplianceImpactResponse,
    ComplianceReadinessBlocker,
    ComplianceReadinessContribution,
    FindingComplianceImpactResponse,
    InspectionComplianceImpactResponse,
)
from app.services.audit_service import record_audit_event
from app.services.compliance.obligation_service import resolve_obligation_compliance


def get_finding_compliance_impact(
    db: Session,
    *,
    organization_id: uuid.UUID,
    finding_id: uuid.UUID,
) -> FindingComplianceImpactResponse:
    """Analyze the compliance and readiness impact of an inspection finding.
    
    Answers:
    - What was found?
    - Which asset/component is affected?
    - Which requirement/obligation is affected?
    - Is this finding blocking operational readiness?
    - What action is required to resolve it?
    """
    finding = db.execute(
        select(Finding).where(
            Finding.id == finding_id,
            Finding.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if finding is None:
        raise NotFoundError("Finding not found")

    obligation: ComplianceObligation | None = None
    req: RegulatoryRequirement | None = None

    # Resolve obligation directly or via requirement
    if finding.compliance_obligation_id is not None:
        obligation = db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.id == finding.compliance_obligation_id,
                ComplianceObligation.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    if obligation is not None and obligation.requirement_id is not None:
        req = db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.id == obligation.requirement_id,
                RegulatoryRequirement.organization_id == organization_id,
            )
        ).scalar_one_or_none()
    elif finding.regulatory_requirement_id is not None:
        req = db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.id == finding.regulatory_requirement_id,
                RegulatoryRequirement.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    # Evidence status linked to this finding
    evidence_items = list(
        db.execute(
            select(Evidence).where(
                Evidence.finding_id == finding.id,
                Evidence.organization_id == organization_id,
            )
        ).scalars().all()
    )

    ev_status: str | None = None
    ev_ver_status: str | None = None
    if evidence_items:
        latest_ev = evidence_items[-1]
        ev_status = latest_ev.status
        ev_ver_status = latest_ev.verification_status

    # Determine readiness blocker status
    is_blocker = False
    blocker_reason: str | None = None

    if finding.status != FindingStatus.CLOSED:
        if finding.severity in {FindingSeverity.CRITICAL, FindingSeverity.MAJOR}:
            is_blocker = True
            blocker_reason = (
                f"Unresolved {finding.severity} finding: {finding.title}. "
                "Must be dispositioned and closed before flight release."
            )
        elif finding.safety_significance in {"FLIGHT_SAFETY", "AIRWORTHINESS"}:
            is_blocker = True
            blocker_reason = (
                f"Unresolved finding with {finding.safety_significance} safety significance: {finding.title}."
            )
        elif obligation is not None and obligation.status in {
            ComplianceState.NON_COMPLIANT.value,
            ComplianceState.OVERDUE.value,
            ComplianceState.BLOCKED.value,
        }:
            is_blocker = True
            blocker_reason = (
                f"Linked compliance obligation is {obligation.status} due to unresolved finding."
            )

    if ev_ver_status == "REJECTED":
        is_blocker = True
        blocker_reason = f"Corrective action evidence for finding was REJECTED: {latest_ev.rejection_reason or 'No reason specified'}."

    # Corrective action required
    corrective_action = None
    if finding.dispositions:
        latest_disp = finding.dispositions[-1]
        corrective_action = latest_disp.corrective_action
    if not corrective_action and finding.status != FindingStatus.CLOSED:
        corrective_action = "Record corrective action disposition and verify closure evidence."

    return FindingComplianceImpactResponse(
        finding_id=finding.id,
        title=finding.title,
        severity=finding.severity,
        status=finding.status,
        safety_significance=finding.safety_significance,
        compliance_relevance=finding.compliance_relevance,
        asset_id=finding.asset_id,
        aircraft_id=finding.aircraft_id,
        component_id=finding.component_id,
        work_order_id=finding.work_order_id,
        inspection_requirement_id=finding.inspection_requirement_id,
        compliance_obligation_id=finding.compliance_obligation_id,
        regulatory_requirement_id=finding.regulatory_requirement_id,
        regulatory_requirement_number=req.requirement_number if req else None,
        regulatory_requirement_title=req.title if req else None,
        current_compliance_state=obligation.status if obligation else None,
        corrective_action_required=corrective_action,
        evidence_status=ev_status,
        evidence_verification_status=ev_ver_status,
        is_readiness_blocker=is_blocker,
        blocker_reason=blocker_reason,
    )


def get_inspection_compliance_impact(
    db: Session,
    *,
    organization_id: uuid.UUID,
    inspection_requirement_id: uuid.UUID,
) -> InspectionComplianceImpactResponse:
    """Analyze how an inspection requirement impacts compliance and operational readiness."""
    insp = db.execute(
        select(InspectionRequirement).where(
            InspectionRequirement.id == inspection_requirement_id,
            InspectionRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if insp is None:
        raise NotFoundError("Inspection requirement not found")

    # Find work order / asset
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    if insp.work_order_id:
        wo = db.execute(
            select(WorkOrder).where(
                WorkOrder.id == insp.work_order_id,
                WorkOrder.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if wo:
            asset_id = wo.asset_id
            aircraft_id = wo.aircraft_id

    # Linked obligation & requirement
    obligation: ComplianceObligation | None = None
    req: RegulatoryRequirement | None = None

    if insp.compliance_obligation_id:
        obligation = db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.id == insp.compliance_obligation_id,
                ComplianceObligation.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    if obligation and obligation.requirement_id:
        req = db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.id == obligation.requirement_id,
                RegulatoryRequirement.organization_id == organization_id,
            )
        ).scalar_one_or_none()
    elif insp.regulatory_requirement_id:
        req = db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.id == insp.regulatory_requirement_id,
                RegulatoryRequirement.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    # Associated findings
    findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.inspection_requirement_id == insp.id,
            )
        ).scalars().all()
    )

    # Attached evidence
    evidence_items = list(
        db.execute(
            select(Evidence).where(
                Evidence.organization_id == organization_id,
                Evidence.inspection_requirement_id == insp.id,
            )
        ).scalars().all()
    )

    # Blocker analysis
    is_blocker = False
    blocker_reason: str | None = None

    if insp.status == InspectionRequirementStatus.REJECTED.value:
        is_blocker = True
        blocker_reason = f"Inspection requirement rejected: {insp.rejection_reason or 'Must be re-inspected.'}"
    elif insp.status == InspectionRequirementStatus.PENDING.value and insp.required:
        is_blocker = True
        blocker_reason = "Mandatory Required Inspection Item (RII) is pending completion by an independent inspector."

    # Check findings
    unresolved_critical = [
        f for f in findings if f.status != FindingStatus.CLOSED and f.severity in {FindingSeverity.CRITICAL, FindingSeverity.MAJOR}
    ]
    if unresolved_critical:
        is_blocker = True
        blocker_reason = (
            f"Inspection produced {len(unresolved_critical)} open critical/major findings requiring disposition."
        )

    # Check evidence verification
    rejected_ev = [
        e for e in evidence_items if e.verification_status == "REJECTED" or e.status == EvidenceStatus.REJECTED.value
    ]
    if rejected_ev:
        is_blocker = True
        blocker_reason = "Inspection evidence was rejected during verification."

    return InspectionComplianceImpactResponse(
        inspection_requirement_id=insp.id,
        status=insp.status,
        required=insp.required,
        inspector_user_id=insp.inspector_user_id,
        work_order_id=insp.work_order_id,
        task_id=insp.task_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        compliance_obligation_id=insp.compliance_obligation_id,
        regulatory_requirement_id=insp.regulatory_requirement_id,
        regulatory_requirement_number=req.requirement_number if req else None,
        current_compliance_state=obligation.status if obligation else None,
        associated_findings=[
            {
                "id": str(f.id),
                "title": f.title,
                "severity": f.severity,
                "status": f.status,
            }
            for f in findings
        ],
        attached_evidence=[
            {
                "id": str(e.id),
                "title": e.title or e.evidence_type,
                "verification_status": e.verification_status,
                "status": e.status,
            }
            for e in evidence_items
        ],
        is_readiness_blocker=is_blocker,
        blocker_reason=blocker_reason,
    )


def resolve_inspection_package_compliance(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    inspection_requirement_id: uuid.UUID,
) -> dict[str, Any]:
    """Evaluate completed inspection package towards linked compliance obligations.
    
    Enforces Phase 6 rules:
    - Inspection must be COMPLETED (or NOT_REQUIRED).
    - Unresolved findings prevent obligation closure.
    - Evidence must be attached and VERIFIED.
    - Deterministic and auditable: never auto-close without satisfying evidence gates.
    """
    insp = db.execute(
        select(InspectionRequirement).where(
            InspectionRequirement.id == inspection_requirement_id,
            InspectionRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if insp is None:
        raise NotFoundError("Inspection requirement not found")

    if insp.status not in {
        InspectionRequirementStatus.COMPLETED.value,
        InspectionRequirementStatus.NOT_REQUIRED.value,
    }:
        raise ConflictError(
            f"Inspection package cannot resolve compliance: status is {insp.status}, not COMPLETED"
        )

    # Check for linked obligation
    obligation: ComplianceObligation | None = None
    if insp.compliance_obligation_id:
        obligation = db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.id == insp.compliance_obligation_id,
                ComplianceObligation.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    if obligation is None:
        return {
            "resolved": False,
            "reason": "No compliance obligation directly linked to this inspection requirement.",
            "inspection_status": insp.status,
        }

    # Check findings gate
    open_findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.inspection_requirement_id == insp.id,
                Finding.status != FindingStatus.CLOSED,
            )
        ).scalars().all()
    )
    if open_findings:
        return {
            "resolved": False,
            "reason": f"Inspection has {len(open_findings)} open findings that must be closed before compliance can be resolved.",
            "obligation_id": str(obligation.id),
            "obligation_status": obligation.status,
        }

    # Resolve obligation compliance using verified evidence
    resolve_obligation_compliance(db, obligation, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(obligation)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="inspection.compliance_resolved",
        entity_type="InspectionRequirement",
        entity_id=insp.id,
        metadata={
            "obligation_id": str(obligation.id),
            "resulting_status": obligation.status,
        },
    )

    return {
        "resolved": obligation.status == ComplianceState.COMPLIANT.value,
        "obligation_id": str(obligation.id),
        "obligation_status": obligation.status,
        "inspection_status": insp.status,
    }


def get_asset_compliance_readiness_contribution(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> ComplianceReadinessContribution:
    """Evaluate multi-threaded compliance, inspection, finding, and evidence status
    for an asset and expose an Authoritative Compliance Readiness Contribution for
    Developer 1's operational readiness gate engine.
    
    Deterministic Gate Rules:
    1. Critical non-compliant obligation -> BLOCKED
    2. Overdue obligation -> BLOCKED
    3. Blocked obligation (INSUFFICIENT_DATA / unknown applicability) -> BLOCKED
    4. Required evidence missing -> BLOCKED
    5. Required evidence rejected -> BLOCKED
    6. Required inspection incomplete or rejected -> BLOCKED
    7. Critical finding unresolved -> BLOCKED
    8. Review-required compliance item -> REVIEW_REQUIRED
    9. Fully satisfied compliance obligations -> READY
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    today = datetime.date.today()

    # 1. Resolve aircraft_id if applicable
    aircraft_id: uuid.UUID | None = None
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.organization_id == organization_id,
            or_(Aircraft.id == asset_id, Aircraft.asset_id == asset_id),
        )
    ).scalar_one_or_none()
    if aircraft:
        aircraft_id = aircraft.id

    blockers: list[ComplianceReadinessBlocker] = []
    warnings: list[str] = []
    source_records: list[dict[str, Any]] = []

    # 2. Query compliance obligations for this asset / aircraft
    obligations = list(
        db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.organization_id == organization_id,
                or_(
                    ComplianceObligation.asset_id == asset_id,
                    ComplianceObligation.aircraft_id == aircraft_id if aircraft_id else False,
                ),
            )
        ).scalars().all()
    )

    compliant_count = 0
    overdue_count = 0
    review_required_count = 0

    for ob in obligations:
        source_records.append(
            {
                "type": "ComplianceObligation",
                "id": str(ob.id),
                "status": ob.status,
                "requirement_id": str(ob.requirement_id),
            }
        )
        req = db.execute(
            select(RegulatoryRequirement).where(
                RegulatoryRequirement.id == ob.requirement_id,
                RegulatoryRequirement.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        req_num = req.requirement_number if req else "REG-REQ"
        req_title = req.title if req else "Regulatory Requirement"

        if ob.status == ComplianceState.COMPLIANT.value:
            compliant_count += 1
        elif ob.status == ComplianceState.NON_COMPLIANT.value:
            blockers.append(
                ComplianceReadinessBlocker(
                    blocker_id=f"COMP-NONCOMPLIANT-{ob.id}",
                    category="NON_COMPLIANT_OBLIGATION",
                    what_blocking=f"Non-compliant regulatory obligation: {req_num}",
                    why_blocking=f"Requirement '{req_title}' is determined NON_COMPLIANT.",
                    source_record_type="ComplianceObligation",
                    source_record_id=ob.id,
                    regulatory_requirement_number=req_num,
                    regulatory_requirement_title=req_title,
                    required_action=ob.required_action or "Execute corrective action",
                    resolution_action="Execute required maintenance action and submit verified evidence.",
                )
            )
        elif ob.status == ComplianceState.OVERDUE.value or (ob.due_date and ob.due_date < today):
            overdue_count += 1
            blockers.append(
                ComplianceReadinessBlocker(
                    blocker_id=f"COMP-OVERDUE-{ob.id}",
                    category="OVERDUE_OBLIGATION",
                    what_blocking=f"Overdue compliance obligation: {req_num}",
                    why_blocking=f"Compliance deadline passed on {ob.due_date}. Mandatory airworthiness directive overdue.",
                    source_record_type="ComplianceObligation",
                    source_record_id=ob.id,
                    regulatory_requirement_number=req_num,
                    regulatory_requirement_title=req_title,
                    required_action=ob.required_action,
                    resolution_action="Perform required compliance action immediately.",
                )
            )
        elif ob.status == ComplianceState.BLOCKED.value:
            blockers.append(
                ComplianceReadinessBlocker(
                    blocker_id=f"COMP-BLOCKED-{ob.id}",
                    category="INSUFFICIENT_DATA",
                    what_blocking=f"Applicability evaluation blocked for: {req_num}",
                    why_blocking=ob.notes or "Applicability condition evaluation incomplete due to missing configuration data.",
                    source_record_type="ComplianceObligation",
                    source_record_id=ob.id,
                    regulatory_requirement_number=req_num,
                    regulatory_requirement_title=req_title,
                    required_action="Provide missing asset configuration attributes.",
                    resolution_action="Update asset configuration to evaluate applicability deterministically.",
                )
            )
        elif ob.status == ComplianceState.REVIEW_REQUIRED.value:
            review_required_count += 1
            warnings.append(f"Compliance review required for {req_num}: {req_title}")

    # 3. Query Findings for this asset
    findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                or_(
                    Finding.asset_id == asset_id,
                    Finding.aircraft_id == aircraft_id if aircraft_id else False,
                ),
            )
        ).scalars().all()
    )

    critical_findings_count = 0
    for finding in findings:
        source_records.append(
            {
                "type": "Finding",
                "id": str(finding.id),
                "title": finding.title,
                "severity": finding.severity,
                "status": finding.status,
            }
        )
        if finding.status != FindingStatus.CLOSED:
            if finding.severity in {FindingSeverity.CRITICAL, FindingSeverity.MAJOR}:
                critical_findings_count += 1
                blockers.append(
                    ComplianceReadinessBlocker(
                        blocker_id=f"FINDING-CRIT-{finding.id}",
                        category="CRITICAL_FINDING",
                        what_blocking=f"Unresolved {finding.severity} finding: {finding.title}",
                        why_blocking=f"Finding severity {finding.severity} constitutes an active airworthiness defect.",
                        source_record_type="Finding",
                        source_record_id=finding.id,
                        required_action=f"Disposition and perform corrective action on finding '{finding.title}'.",
                        resolution_action="Submit corrective action disposition and attach verified completion evidence.",
                    )
                )
            elif finding.safety_significance in {"FLIGHT_SAFETY", "AIRWORTHINESS"}:
                critical_findings_count += 1
                blockers.append(
                    ComplianceReadinessBlocker(
                        blocker_id=f"FINDING-SAFETY-{finding.id}",
                        category="CRITICAL_FINDING",
                        what_blocking=f"Safety-critical finding unresolved: {finding.title}",
                        why_blocking=f"Finding marked with {finding.safety_significance} safety significance.",
                        source_record_type="Finding",
                        source_record_id=finding.id,
                        required_action="Perform safety corrective action.",
                        resolution_action="Close finding with verified evidence.",
                    )
                )
            else:
                warnings.append(f"Open finding ({finding.severity}): {finding.title}")

    # 4. Query Evidence items for this asset & linked obligations
    obligation_ids = [ob.id for ob in obligations]
    evidence_query = select(Evidence).where(
        Evidence.organization_id == organization_id,
        or_(
            Evidence.asset_id == asset_id,
            Evidence.aircraft_id == aircraft_id if aircraft_id else False,
            Evidence.compliance_obligation_id.in_(obligation_ids) if obligation_ids else False,
        ),
    )
    evidence_items = list(db.execute(evidence_query).scalars().all())

    rejected_evidence_count = 0
    missing_evidence_count = 0

    for ev in evidence_items:
        source_records.append(
            {
                "type": "Evidence",
                "id": str(ev.id),
                "title": ev.title or ev.evidence_type,
                "verification_status": ev.verification_status,
                "status": ev.status,
            }
        )
        if ev.verification_status == "REJECTED" or ev.status == EvidenceStatus.REJECTED.value:
            rejected_evidence_count += 1
            blockers.append(
                ComplianceReadinessBlocker(
                    blocker_id=f"EVIDENCE-REJECTED-{ev.id}",
                    category="REJECTED_EVIDENCE",
                    what_blocking=f"Compliance evidence rejected: {ev.title or ev.evidence_type}",
                    why_blocking=f"Evidence verification failed: {ev.rejection_reason or 'Evidence does not satisfy airworthiness criteria.'}",
                    source_record_type="Evidence",
                    source_record_id=ev.id,
                    required_action="Review rejection reason and supply compliant documentation.",
                    missing_evidence="Replacement verified evidence record",
                    resolution_action="Re-submit compliant evidence and obtain independent verification.",
                )
            )

    # Check for obligations missing evidence
    for ob in obligations:
        if ob.status in {ComplianceState.DUE.value, ComplianceState.OVERDUE.value, ComplianceState.IN_PROGRESS.value}:
            ob_ev = [e for e in evidence_items if e.compliance_obligation_id == ob.id]
            if not ob_ev:
                missing_evidence_count += 1
                if ob.status == ComplianceState.OVERDUE.value or (ob.due_date and ob.due_date < today):
                    # Already captured as overdue blocker, record missing evidence note
                    pass
                elif ob.evidence_requirements:
                    blockers.append(
                        ComplianceReadinessBlocker(
                            blocker_id=f"EVIDENCE-MISSING-{ob.id}",
                            category="MISSING_EVIDENCE",
                            what_blocking=f"Required compliance evidence missing for obligation {ob.id}",
                            why_blocking="Obligation requires documentary proof of accomplishment before clearance.",
                            source_record_type="ComplianceObligation",
                            source_record_id=ob.id,
                            missing_evidence=str(ob.evidence_requirements),
                            resolution_action="Upload required proof of accomplishment.",
                        )
                    )

    # 5. Query Inspection Requirements for this asset via work orders
    inspections_query = (
        select(InspectionRequirement)
        .join(WorkOrder, WorkOrder.id == InspectionRequirement.work_order_id)
        .where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
            or_(
                WorkOrder.asset_id == asset_id,
                WorkOrder.aircraft_id == aircraft_id if aircraft_id else False,
            ),
        )
    )
    inspections = list(db.execute(inspections_query).scalars().all())

    for insp in inspections:
        source_records.append(
            {
                "type": "InspectionRequirement",
                "id": str(insp.id),
                "status": insp.status,
                "required": insp.required,
            }
        )
        if insp.status == InspectionRequirementStatus.REJECTED.value:
            blockers.append(
                ComplianceReadinessBlocker(
                    blocker_id=f"INSP-REJECTED-{insp.id}",
                    category="FAILED_INSPECTION",
                    what_blocking="Inspection requirement was rejected.",
                    why_blocking=f"Rejection reason: {insp.rejection_reason or 'Safety inspection criteria not met.'}",
                    source_record_type="InspectionRequirement",
                    source_record_id=insp.id,
                    required_action="Re-open inspection and perform corrective actions.",
                    resolution_action="Perform re-inspection with qualified independent inspector.",
                )
            )
        elif insp.required and insp.status == InspectionRequirementStatus.PENDING.value:
            blockers.append(
                ComplianceReadinessBlocker(
                    blocker_id=f"INSP-PENDING-{insp.id}",
                    category="FAILED_INSPECTION",
                    what_blocking="Mandatory Required Inspection Item (RII) is pending signoff.",
                    why_blocking="Airworthiness release requires independent RII verification.",
                    source_record_type="InspectionRequirement",
                    source_record_id=insp.id,
                    required_action="Independent inspector must inspect and complete signoff.",
                    resolution_action="Complete independent inspection review.",
                )
            )

    # 6. Overall Status Determination
    if blockers:
        overall_status = "BLOCKED"
    elif review_required_count > 0:
        overall_status = "REVIEW_REQUIRED"
    elif not obligations and not findings:
        overall_status = "UNKNOWN"
    else:
        overall_status = "READY"

    return ComplianceReadinessContribution(
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        overall_status=overall_status,
        blockers=blockers,
        warnings=warnings,
        compliance_obligations_count=len(obligations),
        compliant_obligations_count=compliant_count,
        overdue_obligations_count=overdue_count,
        critical_findings_count=critical_findings_count,
        missing_evidence_count=missing_evidence_count,
        rejected_evidence_count=rejected_evidence_count,
        review_required_count=review_required_count,
        source_records=source_records,
        evaluated_at=now,
    )


def get_asset_compliance_impact(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> AssetComplianceImpactResponse:
    """Comprehensive asset-level compliance impact report."""
    contribution = get_asset_compliance_readiness_contribution(
        db, organization_id=organization_id, asset_id=asset_id
    )

    # Critical findings
    findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                or_(
                    Finding.asset_id == asset_id,
                    Finding.aircraft_id == contribution.aircraft_id if contribution.aircraft_id else False,
                ),
                Finding.status != FindingStatus.CLOSED,
            )
        ).scalars().all()
    )
    critical_findings_reports = [
        get_finding_compliance_impact(db, organization_id=organization_id, finding_id=f.id)
        for f in findings
    ]

    # Overdue obligations
    overdue_obligations = list(
        db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.organization_id == organization_id,
                or_(
                    ComplianceObligation.asset_id == asset_id,
                    ComplianceObligation.aircraft_id == contribution.aircraft_id
                    if contribution.aircraft_id
                    else False,
                ),
                ComplianceObligation.status.in_([
                    ComplianceState.OVERDUE.value,
                    ComplianceState.NON_COMPLIANT.value,
                    ComplianceState.BLOCKED.value,
                ]),
            )
        ).scalars().all()
    )

    # Missing or rejected evidence
    obligation_ids = [ob.id for ob in overdue_obligations]
    ev_query = select(Evidence).where(
        Evidence.organization_id == organization_id,
        or_(
            Evidence.asset_id == asset_id,
            Evidence.aircraft_id == contribution.aircraft_id if contribution.aircraft_id else False,
            Evidence.compliance_obligation_id.in_(obligation_ids) if obligation_ids else False,
        ),
        or_(
            Evidence.verification_status == "REJECTED",
            Evidence.status == EvidenceStatus.REJECTED.value,
            Evidence.verification_status == "UNVERIFIED",
        ),
    )
    problem_evidence = list(db.execute(ev_query).scalars().all())

    # Inspections requiring action
    inspections_query = (
        select(InspectionRequirement)
        .join(WorkOrder, WorkOrder.id == InspectionRequirement.work_order_id)
        .where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
            or_(
                WorkOrder.asset_id == asset_id,
                WorkOrder.aircraft_id == contribution.aircraft_id
                if contribution.aircraft_id
                else False,
            ),
            InspectionRequirement.status.in_([
                InspectionRequirementStatus.PENDING.value,
                InspectionRequirementStatus.REJECTED.value,
            ]),
        )
    )
    action_inspections = list(db.execute(inspections_query).scalars().all())
    inspection_reports = [
        get_inspection_compliance_impact(
            db, organization_id=organization_id, inspection_requirement_id=i.id
        )
        for i in action_inspections
    ]

    return AssetComplianceImpactResponse(
        asset_id=asset_id,
        aircraft_id=contribution.aircraft_id,
        overall_status=contribution.overall_status,
        readiness_contribution=contribution,
        active_blockers=contribution.blockers,
        critical_findings=critical_findings_reports,
        overdue_obligations=[
            {
                "id": str(ob.id),
                "requirement_id": str(ob.requirement_id),
                "status": ob.status,
                "due_date": ob.due_date.isoformat() if ob.due_date else None,
                "required_action": ob.required_action,
            }
            for ob in overdue_obligations
        ],
        missing_or_rejected_evidence=[
            {
                "id": str(e.id),
                "title": e.title or e.evidence_type,
                "verification_status": e.verification_status,
                "status": e.status,
                "rejection_reason": e.rejection_reason,
            }
            for e in problem_evidence
        ],
        inspections_requiring_action=inspection_reports,
    )
