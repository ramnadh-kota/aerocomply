import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.battery import Battery
from app.models.flight import Flight
from app.models.user import User
from app.services import drone_service, mission_service
from app.services.audit_service import record_audit_event

# M17.3B: read-side pagination bounds for flight history, same
# conservative-default-plus-hard-max precedent as audit_service's
# AUDIT_LIST_DEFAULT_LIMIT/MAX_LIMIT and installation_service's
# LIFECYCLE_HISTORY_DEFAULT_LIMIT/MAX_LIMIT -- flight history must never
# become an unbounded response for a fleet with a long operational record.
FLIGHT_HISTORY_DEFAULT_LIMIT = 50
FLIGHT_HISTORY_MAX_LIMIT = 100


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
    mission_id: uuid.UUID | None = None,
) -> Flight:
    # Confirms the drone belongs to this tenant before recording a flight
    # against it (cross-tenant IDOR otherwise).
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    # Validate pilot belongs to the caller's organization if provided
    if pilot_user_id is not None:
        pilot = db.execute(
            select(User).where(
                User.id == pilot_user_id,
                User.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if pilot is None:
            raise NotFoundError("Pilot user not found in organization")

    # Validate mission exists in caller's organization and references this asset
    if mission_id is not None:
        mission = mission_service.get_mission(
            db, organization_id=organization_id, mission_id=mission_id
        )
        if mission.asset_id != asset_id:
            raise AeroComplyError("Mission is not assigned to this drone asset")

    flight = Flight(
        organization_id=organization_id,
        asset_id=asset_id,
        mission_id=mission_id,
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
    #
    # M17.3D: this MUST be a single atomic UPDATE (cycle_count = cycle_count
    # + cycles, evaluated server-side), not a Python-side read-modify-write
    # (`battery.cycle_count += cycles`). The latter computes the new value
    # from a value already read into Python and sends it back as a literal;
    # under concurrent flights on the same battery, two transactions can
    # both read the same stale cycle_count before either commits, and the
    # second UPDATE then overwrites the first's increment (a lost update) --
    # reproduced directly against this exact pattern during M17.3D hardening
    # (final cycle_count 3 instead of 7 for two concurrent +3/+4 flights).
    # An atomic UPDATE has no such window: Postgres computes the new value
    # from whatever row version it holds the lock on, so a second writer
    # blocked behind the first's row lock always adds onto the first's
    # already-committed result.
    db.execute(
        update(Battery)
        .where(Battery.organization_id == organization_id, Battery.asset_id == asset_id)
        .values(cycle_count=Battery.cycle_count + cycles)
    )
    # The UPDATE above bypasses the ORM unit-of-work, so any Battery
    # instance already loaded into this session's identity map (e.g. by a
    # caller sharing this session) would otherwise keep a stale
    # cycle_count in memory until re-queried.
    db.expire_all()

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
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    limit: int = FLIGHT_HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
) -> tuple[list[Flight], int]:
    # Confirms the drone belongs to this tenant before returning any
    # flight history for it (cross-tenant IDOR/enumeration otherwise) --
    # same precedent as every other asset-scoped read in this codebase.
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    limit = max(1, min(limit, FLIGHT_HISTORY_MAX_LIMIT))
    offset = max(0, offset)

    filters = (Flight.organization_id == organization_id, Flight.asset_id == asset_id)
    total = db.execute(select(func.count()).select_from(Flight).where(*filters)).scalar_one()
    # flown_at is the domain event time; id (a UUID, not chronological) is
    # only a deterministic tiebreak when two flights share a timestamp --
    # same precedent as audit_service/installation_service's (timestamp,
    # id) sort.
    stmt = (
        select(Flight)
        .where(*filters)
        .order_by(Flight.flown_at.desc(), Flight.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(db.execute(stmt).scalars().all())
    return items, total


def get_flight(db: Session, *, organization_id: uuid.UUID, flight_id: uuid.UUID) -> Flight:
    flight = db.execute(
        select(Flight).where(Flight.id == flight_id, Flight.organization_id == organization_id)
    ).scalar_one_or_none()
    if flight is None:
        raise NotFoundError("Flight not found")
    return flight


def get_utilization(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """Flight records are the sole source of truth for utilization -- this
    SUMs them on read rather than maintaining a separately-editable
    counter, matching the milestone's explicit utilization-integrity
    requirement and this codebase's existing "derive, never store a
    duplicate" convention (see e.g. Part.available_quantity).

    M17.4: `since` (inclusive lower bound: flown_at >= since) is the one
    extension point maintenance_service needs to compute usage accrued
    since a requirement's last accomplishment, without a second SUM
    implementation -- this is still the only place that aggregates Flight
    rows.

    M17.5: `until` (exclusive upper bound: flown_at < until) lets
    maintenance_service bound usage to a single BatteryInstallation/
    ComponentInstallation window (installed_at <= flown_at < removed_at),
    so a flight after an item was removed is never attributed to it."""
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)
    filters = [Flight.organization_id == organization_id, Flight.asset_id == asset_id]
    if since is not None:
        filters.append(Flight.flown_at >= since)
    if until is not None:
        filters.append(Flight.flown_at < until)
    row = db.execute(
        select(
            func.count(Flight.id),
            func.coalesce(func.sum(Flight.duration_minutes), 0),
            func.coalesce(func.sum(Flight.cycles), 0),
        ).where(*filters)
    ).one()
    return {"total_flights": row[0], "total_minutes": int(row[1]), "total_cycles": int(row[2])}
