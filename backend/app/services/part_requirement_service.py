import uuid

from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.part_requirement import PartRequirement, PartRequirementStatus
from app.models.work_order import WorkOrder
from app.schemas.part_requirement import PartRequirementCreateRequest, PartRequirementUpdateRequest
from app.services import part_service, work_order_service
from app.services.audit_service import record_audit_event

# Statuses that mean the requirement is fully settled -- never touched by
# fulfillment allocation or status re-derivation once reached.
_SETTLED_STATUSES = (PartRequirementStatus.FULFILLED, PartRequirementStatus.CANCELLED)


def _derive_status(requirement: PartRequirement, available_quantity: int) -> str:
    """Authoritative status derivation from actual part availability vs. what's
    still needed. Only touches states this slice owns (REQUIRED/SHORT/AVAILABLE);
    ORDERED/RECEIVED/FULFILLED/CANCELLED are set explicitly by later procurement/
    receiving workflows (not yet built) or manual transitions, never inferred here.
    """
    if requirement.status in (
        PartRequirementStatus.ORDERED,
        PartRequirementStatus.RECEIVED,
        PartRequirementStatus.FULFILLED,
        PartRequirementStatus.CANCELLED,
    ):
        return requirement.status
    outstanding = requirement.required_quantity - requirement.fulfilled_quantity
    if outstanding <= 0:
        return PartRequirementStatus.FULFILLED
    if available_quantity >= outstanding:
        return PartRequirementStatus.AVAILABLE
    return PartRequirementStatus.SHORT


def create_part_requirement(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: PartRequirementCreateRequest,
) -> PartRequirement:
    part = part_service.get_part(db, organization_id=organization_id, part_id=payload.part_id)
    # work_order_id / task_id are client-supplied references -- verify each
    # belongs to this organization before linking it (cross-tenant IDOR
    # otherwise).
    work_order_service.get_work_order(
        db, organization_id=organization_id, work_order_id=payload.work_order_id
    )
    if payload.task_id is not None:
        work_order_service.get_task(db, organization_id=organization_id, task_id=payload.task_id)

    requirement = PartRequirement(
        organization_id=organization_id,
        work_order_id=payload.work_order_id,
        task_id=payload.task_id,
        part_id=payload.part_id,
        required_quantity=payload.required_quantity,
        fulfilled_quantity=0,
        priority=payload.priority,
        created_by_user_id=actor_user_id,
    )
    requirement.status = _derive_status(requirement, part.available_quantity)

    db.add(requirement)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="part_requirement.created",
        entity_type="PartRequirement",
        entity_id=requirement.id,
        metadata={"status": requirement.status},
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def get_part_requirement(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID
) -> PartRequirement:
    requirement = db.execute(
        select(PartRequirement).where(
            PartRequirement.id == requirement_id,
            PartRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if requirement is None:
        raise NotFoundError("Part requirement not found")
    return requirement


def list_part_requirements_for_work_order(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> list[PartRequirement]:
    # Same INHERITED-from-WORKORDER cheap join-filter as
    # work_order_service.list_tasks_for_work_order -- hides a
    # PartRequirement from this one operational listing when its parent
    # WorkOrder is soft-deleted, without mutating the PartRequirement row
    # itself or affecting any other query path (e.g. fulfill_from_receipt/
    # recompute_status_for_part above never join through WorkOrder at all,
    # by design -- see their own docstrings on why they operate over raw
    # part_id).
    return list(
        db.execute(
            select(PartRequirement)
            .join(WorkOrder, WorkOrder.id == PartRequirement.work_order_id)
            .where(
                PartRequirement.organization_id == organization_id,
                PartRequirement.work_order_id == work_order_id,
                WorkOrder.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )


def update_part_requirement(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    payload: PartRequirementUpdateRequest,
) -> PartRequirement:
    requirement = get_part_requirement(
        db, organization_id=organization_id, requirement_id=requirement_id
    )
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(requirement, field, value)

    if "status" not in updates:
        part = part_service.get_part(
            db, organization_id=organization_id, part_id=requirement.part_id
        )
        requirement.status = _derive_status(requirement, part.available_quantity)

    db.add(requirement)
    if updates:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="part_requirement.updated",
            entity_type="PartRequirement",
            entity_id=requirement.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(requirement)
    return requirement


def recompute_status_for_part(
    db: Session, *, organization_id: uuid.UUID, part_id: uuid.UUID
) -> list[PartRequirement]:
    """Re-derive status for every open requirement against a part after its
    quantities change (e.g. a receiving or reservation event elsewhere). Only
    touches requirements still in this slice's own state set, per _derive_status.

    Deliberately never touches fulfilled_quantity: an ad hoc stock change
    (receive/reserve/consume/adjust) tells you a part is now AVAILABLE (or
    not), not that any specific PartRequirement has been FULFILLED -- that
    distinction is real and load-bearing (see
    test_receiving_stock_flips_short_requirement_to_available, which expects
    AVAILABLE, not FULFILLED, right after receiving exactly enough stock).
    Actual fulfillment against a specific requirement is
    fulfill_from_receipt below, called only from the PO-receiving flow that
    actually knows which work order/task/part the receipt was for.
    """
    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    requirements = list(
        db.execute(
            select(PartRequirement).where(
                PartRequirement.organization_id == organization_id,
                PartRequirement.part_id == part_id,
            )
        )
        .scalars()
        .all()
    )
    changed = []
    for requirement in requirements:
        new_status = _derive_status(requirement, part.available_quantity)
        if new_status != requirement.status:
            requirement.status = new_status
            db.add(requirement)
            changed.append(requirement)
    if changed:
        db.commit()
        for requirement in changed:
            db.refresh(requirement)
    return requirements


def fulfill_from_receipt(
    db: Session,
    *,
    organization_id: uuid.UUID,
    part_id: uuid.UUID,
    work_order_id: uuid.UUID | None,
    task_id: uuid.UUID | None,
    received_quantity: int,
) -> list[PartRequirement]:
    """Applies an actual physical receipt (M17.6A) to whichever open
    PartRequirement(s) it was ordered against, incrementing
    PartRequirement.fulfilled_quantity -- the column
    release_readiness_service's MATERIAL blocker reads directly
    (app/services/release_readiness_service.py). Before this, nothing ever
    advanced fulfilled_quantity off 0, so a fully-received part requirement
    never cleared its MATERIAL blocker.

    Called from receiving_service.receive_purchase_order, which knows the
    work_order_id/task_id/part_id the receipt was ordered for (via the
    linked ProcurementRequest) -- never from generic inventory receiving,
    which has no such linkage and must not guess one (see
    recompute_status_for_part's docstring).

    Matching: requirements for this part_id, scoped to work_order_id (and to
    task_id when the receipt is task-specific), oldest first, still open
    (not FULFILLED/CANCELLED) and not yet fully covered. A receipt with no
    work_order_id (e.g. a procurement request never linked to a work order)
    has nothing to fulfill, so this is a no-op.

    Concurrency: the increment is a single atomic UPDATE ... SET
    fulfilled_quantity = LEAST(required_quantity, fulfilled_quantity +
    delta), matching this codebase's existing convention of using
    database-atomic operations for concurrent-safe counters (see
    part_service.get_part's for_update=True docstring) instead of an
    application-level read-modify-write: Postgres computes the new value
    from whatever the current row value is at UPDATE time, so two concurrent
    receipts against the same requirement serialize on the row instead of
    one clobbering the other, and the LEAST(...) cap means fulfilled_quantity
    can never be pushed past required_quantity.
    """
    if work_order_id is None or received_quantity <= 0:
        return []

    conditions = [
        PartRequirement.organization_id == organization_id,
        PartRequirement.part_id == part_id,
        PartRequirement.work_order_id == work_order_id,
    ]
    if task_id is not None:
        conditions.append(PartRequirement.task_id == task_id)

    requirements = list(
        db.execute(select(PartRequirement).where(*conditions).order_by(PartRequirement.created_at))
        .scalars()
        .all()
    )

    remaining_to_allocate = received_quantity
    touched_ids: set[uuid.UUID] = set()
    for requirement in requirements:
        if remaining_to_allocate <= 0:
            break
        if requirement.status in _SETTLED_STATUSES:
            continue
        outstanding = requirement.required_quantity - requirement.fulfilled_quantity
        if outstanding <= 0:
            continue
        delta = min(outstanding, remaining_to_allocate)
        db.execute(
            sa_update(PartRequirement)
            .where(
                PartRequirement.id == requirement.id,
                PartRequirement.organization_id == organization_id,
            )
            .values(
                fulfilled_quantity=func.least(
                    PartRequirement.required_quantity,
                    PartRequirement.fulfilled_quantity + delta,
                )
            )
        )
        remaining_to_allocate -= delta
        touched_ids.add(requirement.id)

    if not touched_ids:
        return requirements

    db.flush()
    for requirement in requirements:
        db.refresh(requirement)

    part = part_service.get_part(db, organization_id=organization_id, part_id=part_id)
    for requirement in requirements:
        if requirement.id not in touched_ids:
            continue
        new_status = _derive_status(requirement, part.available_quantity)
        if new_status != requirement.status:
            requirement.status = new_status
            db.add(requirement)
    db.commit()
    for requirement in requirements:
        db.refresh(requirement)
    return requirements
