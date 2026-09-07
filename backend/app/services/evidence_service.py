"""Evidence lifecycle: upload -> submission -> review -> accept/reject.

CRITICAL invariant (ported from the frontend evidence gate semantics, see
frontend/lib/mock/ai/analytics.ts::evaluateExecutionEvidenceGate): only
ACCEPTED evidence satisfies the completion/release gate. SUBMITTED and
AWAITING_REVIEW must never be treated as equivalent to ACCEPTED. Rejected
evidence must be resubmitted (re-uploaded/re-submitted) before it can be
accepted again.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.evidence import Evidence, EvidenceStatus
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
    db: Session, *, organization_id: uuid.UUID, task_id: uuid.UUID, uploaded_by_user_id: uuid.UUID
) -> Evidence:
    evidence = Evidence(
        organization_id=organization_id,
        task_id=task_id,
        uploaded_by_user_id=uploaded_by_user_id,
        status=EvidenceStatus.UPLOADED.value,
    )
    db.add(evidence)
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
