import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.part import Part
from app.schemas.part import PartCreateRequest, PartUpdateRequest
from app.services.audit_service import record_audit_event


def create_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: PartCreateRequest,
) -> Part:
    part = Part(
        organization_id=organization_id,
        part_number=payload.part_number,
        description=payload.description,
        manufacturer=payload.manufacturer,
        condition=payload.condition,
        serial_number=payload.serial_number,
        batch_or_lot=payload.batch_or_lot,
        location=payload.location,
        quantity_on_hand=payload.quantity_on_hand,
        quantity_reserved=payload.quantity_reserved,
    )
    db.add(part)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="part.created",
        entity_type="Part",
        entity_id=part.id,
    )
    db.commit()
    db.refresh(part)
    return part


def get_part(db: Session, *, organization_id: uuid.UUID, part_id: uuid.UUID) -> Part:
    part = db.execute(
        select(Part).where(Part.id == part_id, Part.organization_id == organization_id)
    ).scalar_one_or_none()
    if part is None:
        raise NotFoundError("Part not found")
    return part


def list_parts(db: Session, *, organization_id: uuid.UUID) -> list[Part]:
    return list(
        db.execute(select(Part).where(Part.organization_id == organization_id)).scalars().all()
    )


def update_part(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    payload: PartUpdateRequest,
) -> Part:
    part = get_part(db, organization_id=organization_id, part_id=part_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(part, field, value)

    db.add(part)
    if updates:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="part.updated",
            entity_type="Part",
            entity_id=part.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(part)
    return part


def assign_location(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    part_id: uuid.UUID,
    location_id: uuid.UUID,
) -> Part:
    """Sets Part.location_id, which becomes authoritative over the legacy
    free-text `location` field from this point on (see app/models/part.py).
    """
    from app.services import warehouse_service

    part = get_part(db, organization_id=organization_id, part_id=part_id)
    # Confirm the location belongs to this tenant before assigning it.
    warehouse_service.get_location(db, organization_id=organization_id, location_id=location_id)

    part.location_id = location_id
    db.add(part)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="part.location_assigned",
        entity_type="Part",
        entity_id=part.id,
        metadata={"location_id": str(location_id)},
    )
    db.commit()
    db.refresh(part)
    return part


def get_shortage_status(part: Part) -> bool:
    """A part is in shortage when there is nothing left to allocate: on-hand minus
    reserved has hit zero or gone negative. No severity tiers are inferred here —
    that scoring belongs to a later milestone, not this persistence slice.
    """
    return part.available_quantity <= 0
