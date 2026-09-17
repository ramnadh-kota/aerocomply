import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.battery import Battery
from app.services import drone_service
from app.services.audit_service import record_audit_event


def attach_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    serial_number: str,
    manufacturer: str | None,
    model: str | None,
    capacity_mah: int | None,
    voltage: int | None,
) -> Battery:
    # Confirms the drone belongs to this tenant before attaching a battery
    # to it (cross-tenant IDOR otherwise).
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    battery = Battery(
        organization_id=organization_id,
        asset_id=asset_id,
        serial_number=serial_number,
        manufacturer=manufacturer,
        model=model,
        capacity_mah=capacity_mah,
        voltage=voltage,
    )
    db.add(battery)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="battery.attached",
        entity_type="Battery",
        entity_id=battery.id,
        metadata={"asset_id": str(asset_id), "serial_number": serial_number},
    )
    db.commit()
    db.refresh(battery)
    return battery


def list_batteries_for_asset(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[Battery]:
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)
    return list(
        db.execute(
            select(Battery).where(
                Battery.organization_id == organization_id, Battery.asset_id == asset_id
            )
        )
        .scalars()
        .all()
    )


def get_battery(db: Session, *, organization_id: uuid.UUID, battery_id: uuid.UUID) -> Battery:
    battery = db.execute(
        select(Battery).where(Battery.id == battery_id, Battery.organization_id == organization_id)
    ).scalar_one_or_none()
    if battery is None:
        raise NotFoundError("Battery not found")
    return battery


def update_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    battery_id: uuid.UUID,
    health_percent: int | None,
    status: str | None,
    notes: str | None,
) -> Battery:
    battery = get_battery(db, organization_id=organization_id, battery_id=battery_id)

    updates: dict = {}
    if health_percent is not None:
        battery.health_percent = health_percent
        updates["health_percent"] = health_percent
    if status is not None:
        battery.status = status
        updates["status"] = status
    if notes is not None:
        battery.notes = notes
        updates["notes"] = notes

    db.add(battery)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="battery.updated",
            entity_type="Battery",
            entity_id=battery.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(battery)
    return battery
