import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.vendor import Vendor
from app.schemas.vendor import VendorCreateRequest, VendorUpdateRequest
from app.services.audit_service import record_audit_event


def create_vendor(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: VendorCreateRequest,
) -> Vendor:
    vendor = Vendor(
        organization_id=organization_id,
        name=payload.name,
        contact_email=payload.contact_email,
        location=payload.location,
        certifications=payload.certifications,
        approved=payload.approved,
    )
    db.add(vendor)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="vendor.created",
        entity_type="Vendor",
        entity_id=vendor.id,
    )
    db.commit()
    db.refresh(vendor)
    return vendor


def get_vendor(db: Session, *, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
    vendor = db.execute(
        select(Vendor).where(Vendor.id == vendor_id, Vendor.organization_id == organization_id)
    ).scalar_one_or_none()
    if vendor is None:
        raise NotFoundError("Vendor not found")
    return vendor


def list_vendors(db: Session, *, organization_id: uuid.UUID) -> list[Vendor]:
    return list(
        db.execute(select(Vendor).where(Vendor.organization_id == organization_id))
        .scalars()
        .all()
    )


def update_vendor(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    vendor_id: uuid.UUID,
    payload: VendorUpdateRequest,
) -> Vendor:
    vendor = get_vendor(db, organization_id=organization_id, vendor_id=vendor_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(vendor, field, value)

    db.add(vendor)
    if updates:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="vendor.updated",
            entity_type="Vendor",
            entity_id=vendor.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(vendor)
    return vendor
