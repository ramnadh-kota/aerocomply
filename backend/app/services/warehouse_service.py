import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.warehouse import Location, Warehouse
from app.schemas.warehouse import LocationCreateRequest, WarehouseCreateRequest
from app.services.audit_service import record_audit_event


def create_warehouse(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: WarehouseCreateRequest,
) -> Warehouse:
    existing = db.execute(
        select(Warehouse).where(
            Warehouse.organization_id == organization_id, Warehouse.code == payload.code
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Warehouse code {payload.code!r} already in use", code="duplicate_warehouse_code"
        )

    warehouse = Warehouse(organization_id=organization_id, code=payload.code, name=payload.name)
    db.add(warehouse)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="warehouse.created",
        entity_type="Warehouse",
        entity_id=warehouse.id,
    )
    db.commit()
    db.refresh(warehouse)
    return warehouse


def get_warehouse(
    db: Session, *, organization_id: uuid.UUID, warehouse_id: uuid.UUID
) -> Warehouse:
    warehouse = db.execute(
        select(Warehouse).where(
            Warehouse.id == warehouse_id, Warehouse.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if warehouse is None:
        raise NotFoundError("Warehouse not found")
    return warehouse


def list_warehouses(db: Session, *, organization_id: uuid.UUID) -> list[Warehouse]:
    return list(
        db.execute(select(Warehouse).where(Warehouse.organization_id == organization_id))
        .scalars()
        .all()
    )


def create_location(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    warehouse_id: uuid.UUID,
    payload: LocationCreateRequest,
) -> Location:
    # Confirm the warehouse belongs to this tenant before adding a location to it.
    get_warehouse(db, organization_id=organization_id, warehouse_id=warehouse_id)

    existing = db.execute(
        select(Location).where(
            Location.warehouse_id == warehouse_id, Location.code == payload.code
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Location code {payload.code!r} already in use in this warehouse",
            code="duplicate_location_code",
        )

    location = Location(
        organization_id=organization_id,
        warehouse_id=warehouse_id,
        code=payload.code,
        description=payload.description,
    )
    db.add(location)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="location.created",
        entity_type="Location",
        entity_id=location.id,
        metadata={"warehouse_id": str(warehouse_id)},
    )
    db.commit()
    db.refresh(location)
    return location


def get_location(db: Session, *, organization_id: uuid.UUID, location_id: uuid.UUID) -> Location:
    location = db.execute(
        select(Location).where(
            Location.id == location_id, Location.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if location is None:
        raise NotFoundError("Location not found")
    return location


def list_locations_for_warehouse(
    db: Session, *, organization_id: uuid.UUID, warehouse_id: uuid.UUID
) -> list[Location]:
    get_warehouse(db, organization_id=organization_id, warehouse_id=warehouse_id)
    return list(
        db.execute(
            select(Location).where(
                Location.organization_id == organization_id,
                Location.warehouse_id == warehouse_id,
            )
        )
        .scalars()
        .all()
    )
