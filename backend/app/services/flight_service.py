import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.battery import Battery
from app.models.flight import Flight
from app.services import drone_service
from app.services.audit_service import record_audit_event


def record_flight(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    flown_at: datetime,
    duration_minutes: int,
    cycles: int,
    pilot_user_id: uuid.UUID | None,
    notes: str | None,
) -> Flight:
    # Confirms the drone belongs to this tenant before recording a flight
    # against it (cross-tenant IDOR otherwise).
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    flight = Flight(
        organization_id=organization_id,
        asset_id=asset_id,
        flown_at=flown_at,
        duration_minutes=duration_minutes,
        cycles=cycles,
        pilot_user_id=pilot_user_id,
        notes=notes,
    )
    db.add(flight)
    db.flush()

    # Flight records are the utilization source of truth (see
    # app/models/flight.py's docstring) -- a flight increments the
    # currently-attached battery's cycle_count here, rather than letting a
    # user manually edit it, so the battery's cycles can never drift from
    # its actual flight history.
    attached_battery = db.execute(
        select(Battery).where(
            Battery.organization_id == organization_id, Battery.asset_id == asset_id
        )
    ).scalar_one_or_none()
    if attached_battery is not None:
        attached_battery.cycle_count += cycles
        db.add(attached_battery)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="flight.recorded",
        entity_type="Flight",
        entity_id=flight.id,
        metadata={
            "asset_id": str(asset_id),
            "duration_minutes": duration_minutes,
            "cycles": cycles,
        },
    )
    db.commit()
    db.refresh(flight)
    return flight


def list_flights_for_asset(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[Flight]:
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)
    return list(
        db.execute(
            select(Flight)
            .where(Flight.organization_id == organization_id, Flight.asset_id == asset_id)
            .order_by(Flight.flown_at.desc())
        )
        .scalars()
        .all()
    )


def get_utilization(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> dict:
    """Flight records are the sole source of truth for utilization -- this
    SUMs them on read rather than maintaining a separately-editable
    counter, matching the milestone's explicit utilization-integrity
    requirement and this codebase's existing "derive, never store a
    duplicate" convention (see e.g. Part.available_quantity)."""
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)
    row = db.execute(
        select(
            func.count(Flight.id),
            func.coalesce(func.sum(Flight.duration_minutes), 0),
            func.coalesce(func.sum(Flight.cycles), 0),
        ).where(Flight.organization_id == organization_id, Flight.asset_id == asset_id)
    ).one()
    return {"total_flights": row[0], "total_minutes": int(row[1]), "total_cycles": int(row[2])}
