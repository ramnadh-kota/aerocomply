"""Evidence lifecycle: upload -> submission -> review -> accept/reject.

CRITICAL invariant (ported from the frontend evidence gate semantics, see
frontend/lib/mock/ai/analytics.ts::evaluateExecutionEvidenceGate): only
ACCEPTED evidence satisfies the completion/release gate. SUBMITTED and
AWAITING_REVIEW must never be treated as equivalent to ACCEPTED. Rejected
evidence must be resubmitted (re-uploaded/re-submitted) before it can be
accepted again.
"""
import datetime
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.evidence import Evidence, EvidenceStatus
from app.models.task import Task
from app.services.audit_service import record_audit_event

# Forward lifecycle sequence. REJECTED is reachable from SUBMITTED or
# AWAITING_REVIEW, and rejected evidence can be resubmitted back into the
# forward flow (toward UPLOADED or SUBMITTED) for another review pass.
_FORWARD_SEQUENCE: list[EvidenceStatus] = [
    EvidenceStatus.REQUIRED,
    EvidenceStatus.UPLOADED,
    EvidenceStatus.SUBMITTED,
    EvidenceStatus.AWAITING_REVIEW,
    EvidenceStatus.ACCEPTED,
]

_ALLOWED_TRANSITIONS: dict[EvidenceStatus, set[EvidenceStatus]] = {
    EvidenceStatus.REQUIRED: {EvidenceStatus.UPLOADED},
    EvidenceStatus.UPLOADED: {EvidenceStatus.SUBMITTED},
    EvidenceStatus.SUBMITTED: {EvidenceStatus.AWAITING_REVIEW, EvidenceStatus.REJECTED},
    EvidenceStatus.AWAITING_REVIEW: {
        EvidenceStatus.ACCEPTED,
        EvidenceStatus.REJECTED,
    },
    EvidenceStatus.ACCEPTED: set(),
    # Rejected evidence must be resubmitted, not silently reinstated as accepted.
    EvidenceStatus.REJECTED: {EvidenceStatus.UPLOADED, EvidenceStatus.SUBMITTED},
}


def can_transition(current: EvidenceStatus, target: EvidenceStatus) -> bool:
    """Pure rule check: is `current -> target` a legal evidence status transition?

    No illegal skips (e.g. REQUIRED -> ACCEPTED), no backwards moves within the
    forward sequence, except REJECTED which may re-enter at UPLOADED or SUBMITTED.
    """
    if current == target:
        return False
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def satisfies_completion_gate(status: EvidenceStatus | str) -> bool:
    """Only ACCEPTED evidence satisfies the completion/release gate."""
    value = status.value if isinstance(status, EvidenceStatus) else status
    return value == EvidenceStatus.ACCEPTED.value


def transition_evidence(
    db: Session,
    evidence: Evidence,
    target_status: EvidenceStatus,
    *,
    actor_user_id: uuid.UUID | None,
    rejection_reason: str | None = None,
) -> Evidence:
    current = EvidenceStatus(evidence.status)
    if not can_transition(current, target_status):
        raise ConflictError(
            f"Cannot transition evidence from {current.value} to {target_status.value}"
        )

    evidence.status = target_status.value

    if target_status == EvidenceStatus.REJECTED:
        evidence.rejection_reason = rejection_reason
        evidence.reviewer_user_id = actor_user_id
        record_audit_event(
            db,
            organization_id=evidence.organization_id,
            user_id=actor_user_id,
            action="evidence.rejected",
            entity_type="Evidence",
            entity_id=evidence.id,
            metadata={"rejection_reason": rejection_reason},
        )
    elif target_status == EvidenceStatus.ACCEPTED:
        evidence.rejection_reason = None
        evidence.reviewer_user_id = actor_user_id
        record_audit_event(
            db,
            organization_id=evidence.organization_id,
            user_id=actor_user_id,
            action="evidence.accepted",
            entity_type="Evidence",
            entity_id=evidence.id,
        )
    elif target_status in (EvidenceStatus.UPLOADED, EvidenceStatus.SUBMITTED):
        # Resubmission after rejection (or initial forward progress) clears any
        # stale rejection reason.
        if current == EvidenceStatus.REJECTED:
            evidence.rejection_reason = None

    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


def create_evidence(
    db: Session,
    *,
    organization_id: uuid.UUID,
    task_id: uuid.UUID | None = None,
    uploaded_by_user_id: uuid.UUID | None = None,
    compliance_obligation_id: uuid.UUID | None = None,
    regulatory_requirement_id: uuid.UUID | None = None,
    asset_id: uuid.UUID | None = None,
    aircraft_id: uuid.UUID | None = None,
    component_id: uuid.UUID | None = None,
    inspection_requirement_id: uuid.UUID | None = None,
    finding_id: uuid.UUID | None = None,
    work_order_id: uuid.UUID | None = None,
    title: str | None = None,
    description: str | None = None,
    evidence_type: str = "INSPECTION_RECORD",
    source: str | None = None,
    captured_at: Any = None,
    provenance: dict | None = None,
) -> Evidence:
    # 1. Validate task_id belongs to organization if provided
    if task_id is not None:
        task = db.execute(
            select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
        ).scalar_one_or_none()
        if task is None:
            raise NotFoundError("Task not found")

    # 2. Validate compliance_obligation_id belongs to organization if provided
    obligation = None
    if compliance_obligation_id is not None:
        from app.models.compliance import ComplianceObligation

        obligation = db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.id == compliance_obligation_id,
                ComplianceObligation.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if obligation is None:
            raise NotFoundError("Compliance obligation not found")
        # Auto-inherit requirement_id, asset_id, aircraft_id if not explicitly provided
        if regulatory_requirement_id is None:
            regulatory_requirement_id = obligation.requirement_id
        if asset_id is None and obligation.asset_id is not None:
            asset_id = obligation.asset_id
        if aircraft_id is None and obligation.aircraft_id is not None:
            aircraft_id = obligation.aircraft_id

    evidence = Evidence(
        organization_id=organization_id,
        task_id=task_id,
        compliance_obligation_id=compliance_obligation_id,
        regulatory_requirement_id=regulatory_requirement_id,
        asset_id=asset_id,
        aircraft_id=aircraft_id,
        component_id=component_id,
        inspection_requirement_id=inspection_requirement_id,
        finding_id=finding_id,
        work_order_id=work_order_id,
        title=title,
        description=description,
        evidence_type=evidence_type,
        source=source,
        captured_at=captured_at,
        provenance=provenance,
        uploaded_by_user_id=uploaded_by_user_id,
        status=EvidenceStatus.UPLOADED.value,
        verification_status="UNVERIFIED",
    )
    db.add(evidence)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=uploaded_by_user_id,
        action="evidence.created",
        entity_type="Evidence",
        entity_id=evidence.id,
        metadata={
            "evidence_type": evidence_type,
            "title": title,
            "compliance_obligation_id": str(compliance_obligation_id) if compliance_obligation_id else None,
            "task_id": str(task_id) if task_id else None,
        },
    )

    if obligation is not None:
        from app.services.compliance.obligation_service import resolve_obligation_compliance

        resolve_obligation_compliance(db, obligation, actor_user_id=uploaded_by_user_id)

    db.commit()
    db.refresh(evidence)
    return evidence


def get_evidence(db: Session, *, organization_id: uuid.UUID, evidence_id: uuid.UUID) -> Evidence:
    evidence = db.execute(
        select(Evidence).where(
            Evidence.id == evidence_id, Evidence.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if evidence is None:
        raise NotFoundError("Evidence not found")
    return evidence


def list_evidence(
    db: Session, *, organization_id: uuid.UUID, status: str | None = None, asset_id: uuid.UUID | None = None,
    work_order_id: uuid.UUID | None = None, limit: int = 100, offset: int = 0,
) -> tuple[list[Evidence], int]:
    """Tenant-scoped evidence register (newest first) with optional filters and bounded paging."""
    from sqlalchemy import func

    conds = [Evidence.organization_id == organization_id]
    if status:
        conds.append(Evidence.status == status)
    if asset_id:
        conds.append(Evidence.asset_id == asset_id)
    if work_order_id:
        conds.append(Evidence.work_order_id == work_order_id)
    limit = max(1, min(limit, 200))
    total = db.scalar(select(func.count(Evidence.id)).where(*conds)) or 0
    rows = db.execute(
        select(Evidence).where(*conds).order_by(Evidence.created_at.desc()).limit(limit).offset(max(0, offset))
    ).scalars().all()
    return list(rows), total


def list_evidence_for_task(
    db: Session, *, organization_id: uuid.UUID, task_id: uuid.UUID
) -> list[Evidence]:
    return list(
        db.execute(
            select(Evidence).where(
                Evidence.organization_id == organization_id, Evidence.task_id == task_id
            )
        ).scalars().all()
    )


def list_evidence_for_obligation(
    db: Session, *, organization_id: uuid.UUID, obligation_id: uuid.UUID
) -> list[Evidence]:
    return list(
        db.execute(
            select(Evidence).where(
                Evidence.organization_id == organization_id,
                Evidence.compliance_obligation_id == obligation_id,
            )
        )
        .scalars()
        .all()
    )


def verify_evidence(
    db: Session,
    evidence: Evidence,
    *,
    verifier_user_id: uuid.UUID | None,
    verification_notes: str | None = None,
) -> Evidence:
    """Explicitly verify an evidence record.
    
    Sets verification_status to VERIFIED and status to ACCEPTED.
    Updates any linked compliance obligation, potentially transitioning it to COMPLIANT.
    """
    evidence.verification_status = "VERIFIED"
    evidence.status = EvidenceStatus.ACCEPTED.value
    evidence.verified_at = datetime.datetime.now(datetime.timezone.utc)
    evidence.verifier_user_id = verifier_user_id
    evidence.reviewer_user_id = verifier_user_id
    evidence.verification_notes = verification_notes
    evidence.rejection_reason = None

    record_audit_event(
        db,
        organization_id=evidence.organization_id,
        user_id=verifier_user_id,
        action="evidence.verified",
        entity_type="Evidence",
        entity_id=evidence.id,
        metadata={"verification_notes": verification_notes},
    )

    if evidence.compliance_obligation_id is not None:
        from app.models.compliance import ComplianceObligation
        from app.services.compliance.obligation_service import resolve_obligation_compliance

        obligation = db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.id == evidence.compliance_obligation_id,
                ComplianceObligation.organization_id == evidence.organization_id,
            )
        ).scalar_one_or_none()
        if obligation:
            resolve_obligation_compliance(db, obligation, actor_user_id=verifier_user_id)

    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


def reject_evidence(
    db: Session,
    evidence: Evidence,
    *,
    verifier_user_id: uuid.UUID | None,
    rejection_reason: str,
) -> Evidence:
    """Explicitly reject an evidence record.
    
    Sets verification_status to REJECTED and status to REJECTED.
    Ensures linked compliance obligations cannot be declared COMPLIANT.
    """
    evidence.verification_status = "REJECTED"
    evidence.status = EvidenceStatus.REJECTED.value
    evidence.rejection_reason = rejection_reason
    evidence.verifier_user_id = verifier_user_id
    evidence.reviewer_user_id = verifier_user_id

    record_audit_event(
        db,
        organization_id=evidence.organization_id,
        user_id=verifier_user_id,
        action="evidence.rejected",
        entity_type="Evidence",
        entity_id=evidence.id,
        metadata={"rejection_reason": rejection_reason},
    )

    if evidence.compliance_obligation_id is not None:
        from app.models.compliance import ComplianceObligation
        from app.services.compliance.obligation_service import resolve_obligation_compliance

        obligation = db.execute(
            select(ComplianceObligation).where(
                ComplianceObligation.id == evidence.compliance_obligation_id,
                ComplianceObligation.organization_id == evidence.organization_id,
            )
        ).scalar_one_or_none()
        if obligation:
            resolve_obligation_compliance(db, obligation, actor_user_id=verifier_user_id)

    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence

