"""Inspection requirement lifecycle: PENDING -> COMPLETED / NOT_REQUIRED / REJECTED.

Two real-world concepts this backend must not blur (mirrored from the
frontend's distinction in frontend/lib/mock/ai/analytics.ts —
isInspectionRequired / getInspectionRequirement / getEligibleInspectorsForWorkOrder
— re-implemented here as the backend's own canonical logic, not ported
wholesale):

1. Checklist review — ``required is False``. Any authorized reviewer may
   close it out; there is no independence constraint.
2. RII (Required Inspection Item) — ``required is True``. Completion demands
   an ``inspector_user_id`` who is independent of whoever executed the
   underlying work. This backend has no separate "assigned technician" field
   on Task/WorkOrder, so the executing technician is identified the only
   grounded way available: the user(s) who uploaded evidence for the same
   task (Evidence.uploaded_by_user_id). If no such evidence exists yet, the
   independence check has nothing to compare against and is skipped rather
   than fabricated — but an explicit inspector attempting to sign off on
   their own uploaded evidence is always rejected.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.evidence import Evidence
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.services.audit_service import record_audit_event

_ALLOWED_TRANSITIONS: dict[InspectionRequirementStatus, set[InspectionRequirementStatus]] = {
    InspectionRequirementStatus.PENDING: {
        InspectionRequirementStatus.COMPLETED,
        InspectionRequirementStatus.NOT_REQUIRED,
        InspectionRequirementStatus.REJECTED,
    },
    InspectionRequirementStatus.REJECTED: {InspectionRequirementStatus.PENDING},
    InspectionRequirementStatus.COMPLETED: set(),
    InspectionRequirementStatus.NOT_REQUIRED: set(),
}


def can_transition(
    current: InspectionRequirementStatus, target: InspectionRequirementStatus
) -> bool:
    """Pure rule check: is `current -> target` a legal transition?

    COMPLETED and NOT_REQUIRED are terminal. REJECTED can only return to
    PENDING for re-inspection.
    """
    if current == target:
        return False
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def satisfies_completion_gate(status: InspectionRequirementStatus | str) -> bool:
    """Only COMPLETED (or a not-required item, by definition) clears the gate."""
    value = status.value if isinstance(status, InspectionRequirementStatus) else status
    return value in (
        InspectionRequirementStatus.COMPLETED.value,
        InspectionRequirementStatus.NOT_REQUIRED.value,
    )


def _executing_technician_ids(db: Session, requirement: InspectionRequirement) -> set[uuid.UUID]:
    """Best-effort identification of who performed the work this requirement
    covers, via the task's evidence uploaders. Returns an empty set when this
    cannot be grounded in real data (no task_id, or no evidence yet) — the
    independence check treats an empty set as "cannot verify" rather than
    fabricating a technician.
    """
    if requirement.task_id is None:
        return set()
    rows = db.execute(
        select(Evidence.uploaded_by_user_id).where(
            Evidence.organization_id == requirement.organization_id,
            Evidence.task_id == requirement.task_id,
            Evidence.uploaded_by_user_id.is_not(None),
        )
    ).scalars().all()
    return {uid for uid in rows if uid is not None}


def _assert_independent_inspector(
    db: Session, requirement: InspectionRequirement, inspector_user_id: uuid.UUID | None
) -> None:
    """Enforce the RII independence rule: for a required inspection, the
    inspector must not be the same person who executed the work.
    """
    if not requirement.required:
        return
    if inspector_user_id is None:
        raise ConflictError(
            "An inspector_user_id is required to complete a required (RII) inspection"
        )
    executors = _executing_technician_ids(db, requirement)
    if inspector_user_id in executors:
        raise ConflictError(
            "The inspector must be independent of the technician who performed the work "
            "(RII rule) — this inspector uploaded evidence for the same task"
        )


def transition_inspection_requirement(
    db: Session,
    requirement: InspectionRequirement,
    target_status: InspectionRequirementStatus,
    *,
    actor_user_id: uuid.UUID | None,
    inspector_user_id: uuid.UUID | None = None,
    rejection_reason: str | None = None,
) -> InspectionRequirement:
    current = InspectionRequirementStatus(requirement.status)
    if not can_transition(current, target_status):
        raise ConflictError(
            f"Cannot transition inspection requirement from {current.value} to "
            f"{target_status.value}"
        )

    if target_status == InspectionRequirementStatus.COMPLETED:
        effective_inspector = inspector_user_id or requirement.inspector_user_id
        _assert_independent_inspector(db, requirement, effective_inspector)
        requirement.inspector_user_id = effective_inspector
        requirement.rejection_reason = None
        requirement.status = target_status.value
        record_audit_event(
            db,
            organization_id=requirement.organization_id,
            user_id=actor_user_id,
            action="inspection.completed",
            entity_type="InspectionRequirement",
            entity_id=requirement.id,
            metadata={
                "inspector_user_id": str(effective_inspector) if effective_inspector else None,
                "required": requirement.required,
            },
        )
    elif target_status == InspectionRequirementStatus.REJECTED:
        requirement.status = target_status.value
        requirement.rejection_reason = rejection_reason
        record_audit_event(
            db,
            organization_id=requirement.organization_id,
            user_id=actor_user_id,
            action="inspection.rejected",
            entity_type="InspectionRequirement",
            entity_id=requirement.id,
            metadata={"rejection_reason": rejection_reason},
        )
    elif target_status == InspectionRequirementStatus.NOT_REQUIRED:
        requirement.status = target_status.value
        requirement.rejection_reason = None
        record_audit_event(
            db,
            organization_id=requirement.organization_id,
            user_id=actor_user_id,
            action="inspection.marked_not_required",
            entity_type="InspectionRequirement",
            entity_id=requirement.id,
        )
    elif target_status == InspectionRequirementStatus.PENDING:
        requirement.status = target_status.value
        requirement.rejection_reason = None
        record_audit_event(
            db,
            organization_id=requirement.organization_id,
            user_id=actor_user_id,
            action="inspection.reopened",
            entity_type="InspectionRequirement",
            entity_id=requirement.id,
        )

    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def create_inspection_requirement(
    db: Session,
    *,
    organization_id: uuid.UUID,
    task_id: uuid.UUID | None,
    work_order_id: uuid.UUID | None,
    required: bool,
) -> InspectionRequirement:
    requirement = InspectionRequirement(
        organization_id=organization_id,
        task_id=task_id,
        work_order_id=work_order_id,
        required=required,
        status=InspectionRequirementStatus.PENDING.value,
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


def get_inspection_requirement(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID
) -> InspectionRequirement:
    requirement = db.execute(
        select(InspectionRequirement).where(
            InspectionRequirement.id == requirement_id,
            InspectionRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if requirement is None:
        raise NotFoundError("Inspection requirement not found")
    return requirement


def list_inspection_requirements_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> list[InspectionRequirement]:
    return list(
        db.execute(
            select(InspectionRequirement).where(
                InspectionRequirement.organization_id == organization_id,
                InspectionRequirement.work_order_id == work_order_id,
            )
        ).scalars().all()
    )
