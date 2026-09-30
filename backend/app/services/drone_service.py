"""Phase 18.6: Drone is NOT a new asset identity -- it is Asset with
asset_type=DRONE (app.models.asset.AssetType, anticipated since Phase 1A).
This service is a thin, DRONE-scoped wrapper over the existing Asset
identity -- it never introduces a second identity table. See
alembic/versions/0032_drone_operations.py's docstring for the full
architecture decision.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.asset import Asset, AssetType
from app.services.audit_service import record_audit_event
from app.services.limit_enforcement_service import check_asset_creation_limit


def create_drone(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    registration: str,
    manufacturer: str | None,
    model: str | None,
    serial_number: str | None,
    facility_id: uuid.UUID | None,
) -> Asset:
    check_asset_creation_limit(db, organization_id=organization_id)

    existing = db.execute(
        select(Asset).where(
            Asset.organization_id == organization_id, Asset.registration == registration
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Asset registration {registration!r} already in use", code="duplicate_registration"
        )

    drone = Asset(
        organization_id=organization_id,
        asset_type=AssetType.DRONE.value,
        registration=registration,
        manufacturer=manufacturer,
        model=model,
        serial_number=serial_number,
        status="ACTIVE",
        facility_id=facility_id,
    )
    try:
        with db.begin_nested():  # a lost race must not abort the caller's wider transaction
            db.add(drone)
            db.flush()
    except IntegrityError as exc:
        raise ConflictError(
            f"Asset registration {registration!r} already in use", code="duplicate_registration"
        ) from exc
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="drone.created",
        entity_type="Asset",
        entity_id=drone.id,
        metadata={"registration": registration},
    )
    db.commit()
    db.refresh(drone)
    return drone


def get_drone(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    return get_airframe(db, organization_id=organization_id, asset_id=asset_id, asset_type=AssetType.DRONE.value)


_AIRFRAME_LABELS = {"DRONE": "Drone", "HELICOPTER": "Helicopter", "EVTOL": "eVTOL"}


def get_airframe(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, asset_type: str = "DRONE"
) -> Asset:
    """Tenant-scoped, undeleted Asset of exactly `asset_type` (DRONE / HELICOPTER / EVTOL): the operational
    sub-resources (components, batteries, maintenance, lifecycle) are shared across these airframes, but every
    route only ever sees the type its own suite owns."""
    # deleted_at.is_(None): a soft-deleted drone (Platform Control Plane, see
    # app/services/deletion_service.py) must disappear from every
    # tenant-facing read, same as get_asset -- this function is the drone
    # vertical's own direct Asset query, not built on asset_service.get_asset.
    drone = db.execute(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.organization_id == organization_id,
            Asset.asset_type == asset_type,
            Asset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if drone is None:
        raise NotFoundError(f"{_AIRFRAME_LABELS.get(asset_type, 'Asset')} not found")
    return drone


def list_drones(db: Session, *, organization_id: uuid.UUID) -> list[Asset]:
    return list(
        db.execute(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.asset_type == AssetType.DRONE.value,
                Asset.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )


def update_drone(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    manufacturer: str | None,
    model: str | None,
    status: str | None,
    facility_id: uuid.UUID | None,
) -> Asset:
    drone = get_drone(db, organization_id=organization_id, asset_id=asset_id)

    updates: dict = {}
    if manufacturer is not None:
        drone.manufacturer = manufacturer
        updates["manufacturer"] = manufacturer
    if model is not None:
        drone.model = model
        updates["model"] = model
    if status is not None:
        drone.status = status
        updates["status"] = status
    if facility_id is not None:
        drone.facility_id = facility_id
        updates["facility_id"] = str(facility_id)

    db.add(drone)
    if updates:
        db.flush()
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="drone.updated",
            entity_type="Asset",
            entity_id=drone.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(drone)
    return drone
