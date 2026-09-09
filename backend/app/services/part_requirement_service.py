import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.part_requirement import PartRequirement, PartRequirementStatus
from app.schemas.part_requirement import PartRequirementCreateRequest, PartRequirementUpdateRequest
from app.services import part_service
from app.services.audit_service import record_audit_event


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
    return list(
        db.execute(
            select(PartRequirement).where(
                PartRequirement.organization_id == organization_id,
                PartRequirement.work_order_id == work_order_id,
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
