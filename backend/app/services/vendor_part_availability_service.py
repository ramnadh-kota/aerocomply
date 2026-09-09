import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.vendor_part_availability import VendorPartAvailability
from app.schemas.vendor_part_availability import (
    VendorPartAvailabilityCreateRequest,
    VendorPartAvailabilityUpdateRequest,
)
from app.services import part_service, vendor_service
from app.services.audit_service import record_audit_event


def create_availability(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: VendorPartAvailabilityCreateRequest,
) -> VendorPartAvailability:
    # Confirm both sides of the relationship belong to this tenant before linking them.
    vendor_service.get_vendor(db, organization_id=organization_id, vendor_id=payload.vendor_id)
    part_service.get_part(db, organization_id=organization_id, part_id=payload.part_id)

    availability = VendorPartAvailability(
        organization_id=organization_id,
        vendor_id=payload.vendor_id,
        part_id=payload.part_id,
        availability_status=payload.availability_status,
        quantity_available=payload.quantity_available,
        lead_time_days=payload.lead_time_days,
        unit_price_cents=payload.unit_price_cents,
        currency=payload.currency,
        aog_availability=payload.aog_availability,
        certification_status=payload.certification_status,
    )
    db.add(availability)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="vendor_part_availability.created",
        entity_type="VendorPartAvailability",
        entity_id=availability.id,
    )
    db.commit()
    db.refresh(availability)
    return availability


def get_availability(
    db: Session, *, organization_id: uuid.UUID, availability_id: uuid.UUID
) -> VendorPartAvailability:
    availability = db.execute(
        select(VendorPartAvailability).where(
            VendorPartAvailability.id == availability_id,
            VendorPartAvailability.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if availability is None:
        raise NotFoundError("Vendor part availability not found")
    return availability


def list_availability_for_part(
    db: Session, *, organization_id: uuid.UUID, part_id: uuid.UUID
) -> list[VendorPartAvailability]:
    return list(
        db.execute(
            select(VendorPartAvailability).where(
                VendorPartAvailability.organization_id == organization_id,
                VendorPartAvailability.part_id == part_id,
            )
        )
        .scalars()
        .all()
    )


def update_availability(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    availability_id: uuid.UUID,
    payload: VendorPartAvailabilityUpdateRequest,
) -> VendorPartAvailability:
    availability = get_availability(
        db, organization_id=organization_id, availability_id=availability_id
    )
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(availability, field, value)

    db.add(availability)
    if updates:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="vendor_part_availability.updated",
            entity_type="VendorPartAvailability",
            entity_id=availability.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(availability)
    return availability
