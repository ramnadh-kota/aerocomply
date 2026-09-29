import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.battery import Battery
from app.models.flight import Flight
from app.models.user import User
from app.services import asset_service, drone_service, mission_service
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
    pilot_user_id: uuid.UUID | None = None,
    notes: str | None = None,
    mission_id: uuid.UUID | None = None,
    flight_number: str | None = None,
    origin: str | None = None,
    destination: str | None = None,
    departure_time: datetime | None = None,
    arrival_time: datetime | None = None,
    mission_type: str | None = None,
    status: str = "COMPLETED",
    source: str = "MANUAL",
    source_row_id: str | None = None,
    update_battery: bool = True,
    commit: bool = True,
) -> Flight:
    # Confirms the asset belongs to this tenant before recording a flight
    # against it (cross-tenant IDOR otherwise).
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

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
        flight_number=flight_number.strip() if flight_number else None,
        origin=origin.strip() if origin else None,
        destination=destination.strip() if destination else None,
        departure_time=departure_time,
        arrival_time=arrival_time,
        flown_at=flown_at,
        duration_minutes=duration_minutes,
        cycles=cycles,
        mission_type=mission_type.strip() if mission_type else None,
        status=status,
        source=source,
        source_row_id=source_row_id,
        pilot_user_id=pilot_user_id,
        notes=notes.strip() if notes else None,
    )
    db.add(flight)
    db.flush()

    # Flight records are the utilization source of truth (see
    # app/models/flight.py's docstring) -- a flight increments the
    # currently-attached battery's cycle_count here, rather than letting a
    # user manually edit it, so the battery's cycles can never drift from
    # its actual flight history.
    if update_battery:
        db.execute(
            update(Battery)
            .where(Battery.organization_id == organization_id, Battery.asset_id == asset_id)
            .values(cycle_count=Battery.cycle_count + cycles)
        )
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
            "flight_number": flight.flight_number,
            "duration_minutes": duration_minutes,
            "cycles": cycles,
            "source": source,
        },
    )
    if commit:
        db.commit()
    else:
        # Caller owns the transaction (e.g. telemetry ingestion processes one event atomically).
        db.flush()
    db.refresh(flight)
    return flight


def list_flights_for_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    limit: int = FLIGHT_HISTORY_DEFAULT_LIMIT,
    offset: int = 0,
    mission_type: str | None = None,
    status: str | None = None,
    pilot_user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> tuple[list[Flight], int]:
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    limit = max(1, min(limit, FLIGHT_HISTORY_MAX_LIMIT))
    offset = max(0, offset)

    filter_conditions = [
        Flight.organization_id == organization_id,
        Flight.asset_id == asset_id,
    ]
    if mission_type:
        filter_conditions.append(Flight.mission_type == mission_type)
    if status:
        filter_conditions.append(Flight.status == status)
    if pilot_user_id:
        filter_conditions.append(Flight.pilot_user_id == pilot_user_id)
    if date_from:
        filter_conditions.append(Flight.flown_at >= date_from)
    if date_to:
        filter_conditions.append(Flight.flown_at <= date_to)

    total = db.execute(
        select(func.count()).select_from(Flight).where(*filter_conditions)
    ).scalar_one()

    stmt = (
        select(Flight)
        .where(*filter_conditions)
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
    """M5.3 / M5.13: Authoritative operational state calculation engine.

    Accounting Invariant:
    Current Utilization = Historical Baseline (if present and active)
                        + SUM(Flight records where flown_at >= Baseline.effective_at)
    Flights prior to effective_at remain traceable but are not double-counted.
    """
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # Check for active historical baseline
    baseline = db.execute(
        select(AssetHistoricalBaseline)
        .where(
            AssetHistoricalBaseline.organization_id == organization_id,
            AssetHistoricalBaseline.asset_id == asset_id,
            AssetHistoricalBaseline.is_active.is_(True),
        )
        .order_by(AssetHistoricalBaseline.effective_at.desc())
    ).scalars().first()

    # Total recorded flight count is always total rows for this asset
    total_flights = db.execute(
        select(func.count(Flight.id)).where(
            Flight.organization_id == organization_id,
            Flight.asset_id == asset_id,
        )
    ).scalar_one()

    filters = [Flight.organization_id == organization_id, Flight.asset_id == asset_id]

    baseline_minutes = 0
    baseline_cycles = 0

    if baseline is not None:
        # If since is not bounded or earlier than baseline, carry in baseline values
        if since is None or since <= baseline.effective_at:
            baseline_minutes = int(round(baseline.flight_hours * 60))
            baseline_cycles = baseline.flight_cycles
            filters.append(Flight.flown_at >= baseline.effective_at)
        else:
            filters.append(Flight.flown_at >= since)
    elif since is not None:
        filters.append(Flight.flown_at >= since)

    if until is not None:
        filters.append(Flight.flown_at < until)

    row = db.execute(
        select(
            func.coalesce(func.sum(Flight.duration_minutes), 0),
            func.coalesce(func.sum(Flight.cycles), 0),
        ).where(*filters)
    ).one()

    post_baseline_minutes = int(row[0])
    post_baseline_cycles = int(row[1])

    total_minutes = baseline_minutes + post_baseline_minutes
    total_cycles = baseline_cycles + post_baseline_cycles

    return {
        "total_flights": total_flights,
        "total_minutes": total_minutes,
        "total_cycles": total_cycles,
        "baseline_hours": baseline.flight_hours if baseline else 0.0,
        "baseline_cycles": baseline.flight_cycles if baseline else 0,
        "baseline_effective_at": baseline.effective_at.isoformat() if baseline else None,
    }


# ---------------------------------------------------------------------------
# M5.13: Historical Carry-In Baseline Service
# ---------------------------------------------------------------------------


def create_asset_baseline(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    flight_hours: float,
    flight_cycles: int,
    effective_at: datetime,
    source: str = "MANUAL",
    evidence_reference: str | None = None,
    notes: str | None = None,
) -> AssetHistoricalBaseline:
    # Ensure asset belongs to tenant
    asset_service.get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # Deactivate any previous baseline for this asset so there is only one active baseline
    db.execute(
        update(AssetHistoricalBaseline)
        .where(
            AssetHistoricalBaseline.organization_id == organization_id,
            AssetHistoricalBaseline.asset_id == asset_id,
        )
        .values(is_active=False)
    )

    baseline = AssetHistoricalBaseline(
        organization_id=organization_id,
        asset_id=asset_id,
        flight_hours=max(0.0, float(flight_hours)),
        flight_cycles=max(0, int(flight_cycles)),
        effective_at=effective_at,
        source=source,
        evidence_reference=evidence_reference.strip() if evidence_reference else None,
        notes=notes.strip() if notes else None,
        created_by_user_id=actor_user_id,
        is_active=True,
    )
    db.add(baseline)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="asset.baseline_created",
        entity_type="AssetHistoricalBaseline",
        entity_id=baseline.id,
        metadata={
            "asset_id": str(asset_id),
            "flight_hours": baseline.flight_hours,
            "flight_cycles": baseline.flight_cycles,
            "effective_at": baseline.effective_at.isoformat(),
            "source": source,
        },
    )
    db.commit()
    db.refresh(baseline)
    return baseline


def get_asset_baseline(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetHistoricalBaseline | None:
    return db.execute(
        select(AssetHistoricalBaseline)
        .where(
            AssetHistoricalBaseline.organization_id == organization_id,
            AssetHistoricalBaseline.asset_id == asset_id,
            AssetHistoricalBaseline.is_active.is_(True),
        )
        .order_by(AssetHistoricalBaseline.effective_at.desc())
    ).scalars().first()


def list_asset_baselines(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[AssetHistoricalBaseline]:
    return list(
        db.execute(
            select(AssetHistoricalBaseline)
            .where(
                AssetHistoricalBaseline.organization_id == organization_id,
                AssetHistoricalBaseline.asset_id == asset_id,
            )
            .order_by(AssetHistoricalBaseline.created_at.desc())
        )
        .scalars()
        .all()
    )

