import datetime
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.battery import Battery
from app.models.component import Component
from app.models.installation_history import BatteryInstallation, ComponentInstallation
from app.models.maintenance_requirement import (
    MaintenanceAccomplishment,
    MaintenanceIntervalType,
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)
from app.schemas.maintenance_requirement import (
    AssetMaintenanceAccomplishmentCreateRequest,
    MaintenanceAccomplishmentCreateRequest,
    MaintenanceApplicabilityCreateRequest,
    MaintenanceDueItem,
    MaintenanceRequirementCreateRequest,
    MaintenanceRequirementResponse,
)
from app.services import (
    aircraft_service,
    battery_service,
    component_service,
    drone_service,
    flight_service,
)
from app.services.asset_resolution import resolve_asset_id
from app.services.audit_service import record_audit_event

# A calendar-interval requirement is DUE_SOON inside this window — matches the
# 30-day horizon convention already used for TAT AT_RISK elsewhere in this
# codebase (see tat_service's documented threshold), kept consistent rather
# than inventing a different number for maintenance.
_DUE_SOON_WINDOW_DAYS = 30

# M17.4A/B: usage-based (FLIGHT_HOURS/FLIGHT_CYCLES) analog of the calendar
# window above. MaintenanceRequirement has no per-record configurable
# warning threshold (adding one would need a migration this milestone's own
# inspection found no concrete need for yet -- see the M17.4 final report's
# "Reset / Interval Model" section) so, exactly like
# _DUE_SOON_WINDOW_DAYS, this is one fixed, documented constant: a
# requirement is DUE_SOON once 90% of its interval has been consumed.
_DUE_SOON_USAGE_FRACTION = 0.9


def create_requirement(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: MaintenanceRequirementCreateRequest,
) -> MaintenanceRequirement:
    requirement = MaintenanceRequirement(
        organization_id=organization_id,
        description=payload.description,
        ata_chapter=payload.ata_chapter,
        interval_type=payload.interval_type,
        fh_interval=payload.fh_interval,
        fc_interval=payload.fc_interval,
        calendar_interval_days=payload.calendar_interval_days,
        task_reference=payload.task_reference,
    )
    db.add(requirement)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_requirement.created",
        entity_type="MaintenanceRequirement",
        entity_id=requirement.id,
    )
    db.commit()
    db.refresh(requirement)
    return requirement


def get_requirement(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID
) -> MaintenanceRequirement:
    requirement = db.execute(
        select(MaintenanceRequirement).where(
            MaintenanceRequirement.id == requirement_id,
            MaintenanceRequirement.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if requirement is None:
        raise NotFoundError("Maintenance requirement not found")
    return requirement


def list_requirements(db: Session, *, organization_id: uuid.UUID) -> list[MaintenanceRequirement]:
    return list(
        db.execute(
            select(MaintenanceRequirement).where(
                MaintenanceRequirement.organization_id == organization_id
            )
        )
        .scalars()
        .all()
    )


def add_applicability(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    payload: MaintenanceApplicabilityCreateRequest,
) -> MaintenanceRequirement:
    requirement = get_requirement(
        db, organization_id=organization_id, requirement_id=requirement_id
    )
    aircraft = aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    applicability = MaintenanceRequirementApplicability(
        organization_id=organization_id,
        requirement_id=requirement.id,
        aircraft_id=payload.aircraft_id,
        asset_id=resolve_asset_id(aircraft),
    )
    db.add(applicability)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_requirement.applicability_added",
        entity_type="MaintenanceRequirement",
        entity_id=requirement.id,
        metadata={"aircraft_id": str(payload.aircraft_id)},
    )
    db.commit()
    return requirement


def record_accomplishment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    payload: MaintenanceAccomplishmentCreateRequest,
) -> MaintenanceAccomplishment:
    get_requirement(db, organization_id=organization_id, requirement_id=requirement_id)
    aircraft = aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    accomplishment = MaintenanceAccomplishment(
        organization_id=organization_id,
        requirement_id=requirement_id,
        aircraft_id=payload.aircraft_id,
        asset_id=resolve_asset_id(aircraft),
        accomplished_at=payload.accomplished_at,
        work_order_id=payload.work_order_id,
        notes=payload.notes,
    )
    db.add(accomplishment)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_accomplishment.recorded",
        entity_type="MaintenanceAccomplishment",
        entity_id=accomplishment.id,
        metadata={"requirement_id": str(requirement_id), "aircraft_id": str(payload.aircraft_id)},
    )
    db.commit()
    db.refresh(accomplishment)
    return accomplishment


def _latest_accomplishment(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID, aircraft_id: uuid.UUID
) -> MaintenanceAccomplishment | None:
    return (
        db.execute(
            select(MaintenanceAccomplishment)
            .where(
                MaintenanceAccomplishment.organization_id == organization_id,
                MaintenanceAccomplishment.requirement_id == requirement_id,
                MaintenanceAccomplishment.aircraft_id == aircraft_id,
            )
            .order_by(MaintenanceAccomplishment.accomplished_at.desc())
        )
        .scalars()
        .first()
    )


# M17.5A: which existing interval column each usage-based metric reads.
# No new columns were added for BATTERY_CYCLES/COMPONENT_HOURS/
# COMPONENT_CYCLES -- they reuse fc_interval/fh_interval exactly like
# FLIGHT_CYCLES/FLIGHT_HOURS already did, distinguished only by
# interval_type.
_HOURS_METRICS = (MaintenanceIntervalType.FLIGHT_HOURS, MaintenanceIntervalType.COMPONENT_HOURS)
_CYCLES_METRICS = (
    MaintenanceIntervalType.FLIGHT_CYCLES,
    MaintenanceIntervalType.BATTERY_CYCLES,
    MaintenanceIntervalType.COMPONENT_CYCLES,
)


def _usage_due_status_for(
    requirement: MaintenanceRequirement, current_usage: float
) -> tuple[str, str, float]:
    """M17.4B/M17.5B: evaluation for every usage-based metric (FLIGHT_HOURS/
    FLIGHT_CYCLES/BATTERY_CYCLES/COMPONENT_HOURS/COMPONENT_CYCLES) -- one
    function, since the arithmetic is identical regardless of what's being
    measured or which authoritative usage source fed `current_usage`
    (flight_service.get_utilization for all of them; this function does no
    independent counting). Returns (status, reason, remaining_usage).
    remaining_usage is clamped at 0, never negative, even once OVERDUE."""
    if requirement.interval_type in _HOURS_METRICS:
        interval = requirement.fh_interval
        unit = "hours"
    elif requirement.interval_type in _CYCLES_METRICS:
        interval = requirement.fc_interval
        unit = "cycles"
    else:
        return "UNKNOWN", "Requirement is not a usage-based metric.", 0.0
    if interval is None:
        return "UNKNOWN", f"Requirement has no {unit[:-1]} interval on file.", 0.0

    remaining = max(0.0, interval - current_usage)
    if current_usage >= interval:
        return (
            "OVERDUE",
            f"{current_usage:.1f} {unit} accumulated, {interval} {unit} interval exceeded.",
            remaining,
        )
    if current_usage >= interval * _DUE_SOON_USAGE_FRACTION:
        return (
            "DUE_SOON",
            f"{current_usage:.1f} of {interval} {unit} used, {remaining:.1f} {unit} remaining.",
            remaining,
        )
    return (
        "NOT_DUE",
        f"{current_usage:.1f} of {interval} {unit} used, {remaining:.1f} {unit} remaining.",
        remaining,
    )


def _due_status_for(
    requirement: MaintenanceRequirement, last_accomplished_at: datetime.date | None
) -> tuple[str, datetime.date | None, str]:
    if requirement.interval_type in (
        MaintenanceIntervalType.FLIGHT_HOURS,
        MaintenanceIntervalType.FLIGHT_CYCLES,
    ):
        # Calendar-only caller (aircraft path): aircraft flight-hour/cycle
        # utilization is still not tracked in this system (only Drone/Asset
        # utilization exists, via flight_service -- see
        # _get_asset_due_item for the asset path that DOES evaluate this).
        return (
            "UNKNOWN",
            None,
            "Aircraft flight-hour/flight-cycle utilization is not tracked in this system.",
        )

    if requirement.calendar_interval_days is None:
        return "UNKNOWN", None, "Requirement has no calendar interval on file."

    if last_accomplished_at is None:
        return (
            "UNKNOWN",
            None,
            "No accomplishment record exists yet — there is no baseline date to compute from.",
        )

    due_date = last_accomplished_at + datetime.timedelta(days=requirement.calendar_interval_days)
    days_until_due = (due_date - datetime.date.today()).days
    due_str = due_date.isoformat()
    if days_until_due < 0:
        return "OVERDUE", due_date, f"Due date {due_str} has passed."
    if days_until_due <= _DUE_SOON_WINDOW_DAYS:
        return "DUE_SOON", due_date, f"Due date {due_str} is within {_DUE_SOON_WINDOW_DAYS} days."
    return "NOT_DUE", due_date, f"Due date {due_str} is more than {_DUE_SOON_WINDOW_DAYS} days out."


def get_maintenance_due_for_aircraft(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> list[MaintenanceDueItem]:
    aircraft_service.get_aircraft(db, organization_id=organization_id, aircraft_id=aircraft_id)

    applicable_requirement_ids = (
        db.execute(
            select(MaintenanceRequirementApplicability.requirement_id).where(
                MaintenanceRequirementApplicability.organization_id == organization_id,
                MaintenanceRequirementApplicability.aircraft_id == aircraft_id,
            )
        )
        .scalars()
        .all()
    )

    items: list[MaintenanceDueItem] = []
    for requirement_id in applicable_requirement_ids:
        requirement = get_requirement(
            db, organization_id=organization_id, requirement_id=requirement_id
        )
        latest = _latest_accomplishment(
            db,
            organization_id=organization_id,
            requirement_id=requirement_id,
            aircraft_id=aircraft_id,
        )
        last_date = latest.accomplished_at if latest else None
        status, due_date, reason = _due_status_for(requirement, last_date)
        items.append(
            MaintenanceDueItem(
                requirement=MaintenanceRequirementResponse.model_validate(requirement),
                aircraft_id=aircraft_id,
                last_accomplished_at=last_date,
                due_status=status,
                due_date=due_date,
                reason=reason,
            )
        )
    return items


def get_fleet_maintenance_due(
    db: Session, *, organization_id: uuid.UUID
) -> list[MaintenanceDueItem]:
    aircraft_ids = [
        a.id for a in aircraft_service.list_aircraft(db, organization_id=organization_id)
    ]
    items: list[MaintenanceDueItem] = []
    for aircraft_id in aircraft_ids:
        items.extend(
            get_maintenance_due_for_aircraft(
                db, organization_id=organization_id, aircraft_id=aircraft_id
            )
        )
    return items


def _latest_accomplishment_for_asset(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID, asset_id: uuid.UUID
) -> MaintenanceAccomplishment | None:
    return (
        db.execute(
            select(MaintenanceAccomplishment)
            .where(
                MaintenanceAccomplishment.organization_id == organization_id,
                MaintenanceAccomplishment.requirement_id == requirement_id,
                MaintenanceAccomplishment.asset_id == asset_id,
            )
            .order_by(MaintenanceAccomplishment.accomplished_at.desc())
        )
        .scalars()
        .first()
    )


def _evaluate_for_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID,
    requirement: MaintenanceRequirement,
) -> MaintenanceDueItem:
    """M17.4B: the one evaluator for an asset(Drone)-linked requirement,
    covering both CALENDAR (delegates to the existing _due_status_for --
    unchanged) and FLIGHT_HOURS/FLIGHT_CYCLES (new: uses
    flight_service.get_utilization, filtered to flights since the last
    accomplishment -- or all flights if none exists yet -- as the reset
    baseline). has_overdue_maintenance_for_asset and
    get_maintenance_due_for_asset both call this so there is exactly one
    place the asset-path evaluation logic lives."""
    latest = _latest_accomplishment_for_asset(
        db, organization_id=organization_id, requirement_id=requirement.id, asset_id=asset_id
    )
    last_date = latest.accomplished_at if latest else None

    if requirement.interval_type == MaintenanceIntervalType.CALENDAR:
        status, due_date, reason = _due_status_for(requirement, last_date)
        return MaintenanceDueItem(
            requirement=MaintenanceRequirementResponse.model_validate(requirement),
            asset_id=asset_id,
            last_accomplished_at=last_date,
            due_status=status,
            due_date=due_date,
            reason=reason,
        )

    # Usage since the reset baseline: last accomplishment date (midnight,
    # naive -- Flight.flown_at is timezone-aware, so this is interpreted as
    # UTC midnight, consistent with this codebase's existing convention of
    # treating a bare `date` as a UTC calendar date elsewhere) or, absent
    # any accomplishment yet, every flight this asset has ever logged.
    since = (
        datetime.datetime.combine(last_date, datetime.time.min, tzinfo=datetime.UTC)
        if last_date is not None
        else None
    )
    utilization = flight_service.get_utilization(
        db, organization_id=organization_id, asset_id=asset_id, since=since
    )
    current_usage = (
        utilization["total_minutes"] / 60.0
        if requirement.interval_type == MaintenanceIntervalType.FLIGHT_HOURS
        else float(utilization["total_cycles"])
    )
    status, reason, remaining = _usage_due_status_for(requirement, current_usage)
    return MaintenanceDueItem(
        requirement=MaintenanceRequirementResponse.model_validate(requirement),
        asset_id=asset_id,
        last_accomplished_at=last_date,
        due_status=status,
        due_date=None,
        reason=reason,
        current_usage=current_usage if status != "UNKNOWN" else None,
        remaining_usage=remaining if status != "UNKNOWN" else None,
    )


def has_overdue_maintenance_for_asset(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> bool:
    """Phase 18.6 / M17.4B: read-only, asset_id-filtered variant for
    Deployment Readiness -- reuses _evaluate_for_asset (the same
    calculation get_maintenance_due_for_asset uses), queried by
    MaintenanceRequirementApplicability.asset_id (the Phase 1B compatibility
    column) instead of aircraft_id, so a Drone (which has no Aircraft row)
    can be evaluated too. A drone with no applicable requirements yet
    honestly has no overdue maintenance, which is what this returns
    (False), not a fabricated status."""
    for item in get_maintenance_due_for_asset(
        db, organization_id=organization_id, asset_id=asset_id
    ):
        if item.due_status == "OVERDUE":
            return True
    return False


def get_maintenance_due_for_asset(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[MaintenanceDueItem]:
    """M17.4B: the asset(Drone) counterpart of get_maintenance_due_for_aircraft
    -- same shape, same tenant-scoping convention, but resolving usage-based
    requirements against real flight utilization instead of returning
    UNKNOWN unconditionally."""
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    applicable_requirement_ids = (
        db.execute(
            select(MaintenanceRequirementApplicability.requirement_id).where(
                MaintenanceRequirementApplicability.organization_id == organization_id,
                MaintenanceRequirementApplicability.asset_id == asset_id,
            )
        )
        .scalars()
        .all()
    )
    items: list[MaintenanceDueItem] = []
    for requirement_id in applicable_requirement_ids:
        requirement = get_requirement(
            db, organization_id=organization_id, requirement_id=requirement_id
        )
        items.append(
            _evaluate_for_asset(
                db, organization_id=organization_id, asset_id=asset_id, requirement=requirement
            )
        )
    return items


def add_applicability_for_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    asset_id: uuid.UUID,
) -> MaintenanceRequirement:
    requirement = get_requirement(
        db, organization_id=organization_id, requirement_id=requirement_id
    )
    # Confirms the drone belongs to this tenant before linking a
    # requirement to it (cross-tenant IDOR otherwise) -- same precedent as
    # every other asset-scoped write in this codebase.
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    applicability = MaintenanceRequirementApplicability(
        organization_id=organization_id,
        requirement_id=requirement.id,
        aircraft_id=None,
        asset_id=asset_id,
    )
    db.add(applicability)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_requirement.applicability_added",
        entity_type="MaintenanceRequirement",
        entity_id=requirement.id,
        metadata={"asset_id": str(asset_id)},
    )
    db.commit()
    return requirement


def record_accomplishment_for_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: AssetMaintenanceAccomplishmentCreateRequest,
) -> MaintenanceAccomplishment:
    get_requirement(db, organization_id=organization_id, requirement_id=requirement_id)
    drone_service.get_drone(db, organization_id=organization_id, asset_id=asset_id)

    accomplishment = MaintenanceAccomplishment(
        organization_id=organization_id,
        requirement_id=requirement_id,
        aircraft_id=None,
        asset_id=asset_id,
        accomplished_at=payload.accomplished_at,
        work_order_id=payload.work_order_id,
        notes=payload.notes,
    )
    db.add(accomplishment)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_accomplishment.recorded",
        entity_type="MaintenanceAccomplishment",
        entity_id=accomplishment.id,
        metadata={"requirement_id": str(requirement_id), "asset_id": str(asset_id)},
    )
    db.commit()
    db.refresh(accomplishment)
    return accomplishment


# ---------------------------------------------------------------------------
# M17.5A/B: Battery/Component maintenance. Extends the same
# MaintenanceRequirement/MaintenanceRequirementApplicability/
# MaintenanceAccomplishment architecture used above for aircraft/asset --
# never a second maintenance system.
#
# LIFETIME USAGE vs USAGE SINCE LAST MAINTENANCE (the critical domain rule):
#   - lifetime_usage on a MaintenanceDueItem is the item's total usage
#     ever, across every installation it has ever had. A maintenance
#     accomplishment never resets it.
#   - current_usage (existing field, unchanged meaning from M17.4) is
#     usage accrued only since the requirement's last accomplishment for
#     THIS item -- what due_status is actually computed from.
#   For Battery, lifetime usage is simply Battery.cycle_count (already
#   correct and already installation-aware -- see M17.3D: cycle_count is a
#   column on the Battery row itself, only ever incremented by a flight
#   while that specific battery is the one attached to an asset, so
#   removing Battery A and installing Battery B already stops A's counter
#   and starts B's, with zero code changes needed here). For Component,
#   no lifetime counter exists anywhere in this codebase, so it is derived
#   the same way "usage since last accomplishment" is: by summing
#   flight_service.get_utilization across every ComponentInstallation
#   window this component has ever had.
# ---------------------------------------------------------------------------


def _installation_windows(
    installations: "Sequence[BatteryInstallation] | Sequence[ComponentInstallation]",
    *,
    current_asset_id: uuid.UUID | None,
    current_installed_at: datetime.datetime | None,
    fallback_installed_at: datetime.datetime,
) -> list[tuple[uuid.UUID, datetime.datetime, datetime.datetime | None]]:
    """M17.5A: battery_service.attach_battery/component_service.attach_component
    (M17.2A's original attach path) set Battery.asset_id/Component.asset_id
    directly and never create a BatteryInstallation/ComponentInstallation
    row -- only the separate installation_service.install_*/remove_*
    functions do. So an item currently attached via the original attach
    path has real usage but zero installation-history rows. Rather than
    reporting that usage as unknowable, synthesize one open window for the
    CURRENT attachment when no installation row already covers it --
    anchored to Battery.installed_at/Component's own installed_at if set
    (install_battery/install_component do set it), else the item's
    created_at (the earliest fact actually on record) as a deliberately
    conservative fallback. This never invents a number: it only widens
    which flights get correctly counted for a real, currently-attached
    item; it is a no-op once every attachment goes through
    installation_service (the fallback branch never fires if a matching
    open row already exists)."""
    windows = [(inst.asset_id, inst.installed_at, inst.removed_at) for inst in installations]
    if current_asset_id is None:
        return windows
    has_open_window_for_current = any(
        asset_id == current_asset_id and removed_at is None for asset_id, _, removed_at in windows
    )
    if not has_open_window_for_current:
        windows.append(
            (current_asset_id, current_installed_at or fallback_installed_at, None)
        )
    return windows


def _usage_across_windows(
    db: Session,
    *,
    organization_id: uuid.UUID,
    windows: list[tuple[uuid.UUID, datetime.datetime, datetime.datetime | None]],
    since: datetime.datetime | None,
) -> tuple[float, float]:
    """Sums flight_service.get_utilization across every installation window,
    each bounded to [max(installed_at, since), removed_at) so a flight
    after an item was removed -- or before `since` -- is never attributed
    to it. Never a second Flight-aggregation implementation: every number
    here comes from flight_service.get_utilization. Returns
    (total_hours, total_cycles)."""
    total_minutes = 0
    total_cycles = 0
    for asset_id, installed_at, removed_at in windows:
        window_start = installed_at if since is None else max(installed_at, since)
        if removed_at is not None and window_start >= removed_at:
            continue
        utilization = flight_service.get_utilization(
            db,
            organization_id=organization_id,
            asset_id=asset_id,
            since=window_start,
            until=removed_at,
        )
        total_minutes += utilization["total_minutes"]
        total_cycles += utilization["total_cycles"]
    return total_minutes / 60.0, float(total_cycles)


def _accomplished_at_to_datetime(
    accomplished_at: datetime.date | None,
) -> datetime.datetime | None:
    if accomplished_at is None:
        return None
    return datetime.datetime.combine(accomplished_at, datetime.time.min, tzinfo=datetime.UTC)


def _latest_accomplishment_for_battery(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID, battery_id: uuid.UUID
) -> MaintenanceAccomplishment | None:
    return (
        db.execute(
            select(MaintenanceAccomplishment)
            .where(
                MaintenanceAccomplishment.organization_id == organization_id,
                MaintenanceAccomplishment.requirement_id == requirement_id,
                MaintenanceAccomplishment.battery_id == battery_id,
            )
            .order_by(MaintenanceAccomplishment.accomplished_at.desc())
        )
        .scalars()
        .first()
    )


def _latest_accomplishment_for_component(
    db: Session, *, organization_id: uuid.UUID, requirement_id: uuid.UUID, component_id: uuid.UUID
) -> MaintenanceAccomplishment | None:
    return (
        db.execute(
            select(MaintenanceAccomplishment)
            .where(
                MaintenanceAccomplishment.organization_id == organization_id,
                MaintenanceAccomplishment.requirement_id == requirement_id,
                MaintenanceAccomplishment.component_id == component_id,
            )
            .order_by(MaintenanceAccomplishment.accomplished_at.desc())
        )
        .scalars()
        .first()
    )


def _evaluate_for_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    battery: Battery,
    requirement: MaintenanceRequirement,
) -> MaintenanceDueItem:
    latest = _latest_accomplishment_for_battery(
        db, organization_id=organization_id, requirement_id=requirement.id, battery_id=battery.id
    )
    last_date = latest.accomplished_at if latest else None
    windows = _installation_windows(
        db.execute(
            select(BatteryInstallation).where(
                BatteryInstallation.organization_id == organization_id,
                BatteryInstallation.battery_id == battery.id,
            )
        )
        .scalars()
        .all(),
        current_asset_id=battery.asset_id,
        current_installed_at=battery.installed_at,
        fallback_installed_at=battery.created_at,
    )
    _, cycles_since = _usage_across_windows(
        db,
        organization_id=organization_id,
        windows=windows,
        since=_accomplished_at_to_datetime(last_date),
    )
    status, reason, remaining = _usage_due_status_for(requirement, cycles_since)
    return MaintenanceDueItem(
        requirement=MaintenanceRequirementResponse.model_validate(requirement),
        battery_id=battery.id,
        last_accomplished_at=last_date,
        due_status=status,
        due_date=None,
        reason=reason,
        current_usage=cycles_since if status != "UNKNOWN" else None,
        remaining_usage=remaining if status != "UNKNOWN" else None,
        lifetime_usage=float(battery.cycle_count),
    )


def _evaluate_for_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    component: Component,
    requirement: MaintenanceRequirement,
) -> MaintenanceDueItem:
    latest = _latest_accomplishment_for_component(
        db,
        organization_id=organization_id,
        requirement_id=requirement.id,
        component_id=component.id,
    )
    last_date = latest.accomplished_at if latest else None
    windows = _installation_windows(
        db.execute(
            select(ComponentInstallation).where(
                ComponentInstallation.organization_id == organization_id,
                ComponentInstallation.component_id == component.id,
            )
        )
        .scalars()
        .all(),
        current_asset_id=component.asset_id,
        current_installed_at=None,  # Component has no installed_at column
        fallback_installed_at=component.created_at,
    )
    hours_since, cycles_since = _usage_across_windows(
        db,
        organization_id=organization_id,
        windows=windows,
        since=_accomplished_at_to_datetime(last_date),
    )
    current_usage = (
        hours_since if requirement.interval_type == MaintenanceIntervalType.COMPONENT_HOURS
        else cycles_since
    )
    status, reason, remaining = _usage_due_status_for(requirement, current_usage)

    lifetime_hours, lifetime_cycles = _usage_across_windows(
        db, organization_id=organization_id, windows=windows, since=None
    )
    lifetime_usage = (
        lifetime_hours
        if requirement.interval_type == MaintenanceIntervalType.COMPONENT_HOURS
        else lifetime_cycles
    )
    return MaintenanceDueItem(
        requirement=MaintenanceRequirementResponse.model_validate(requirement),
        component_id=component.id,
        last_accomplished_at=last_date,
        due_status=status,
        due_date=None,
        reason=reason,
        current_usage=current_usage if status != "UNKNOWN" else None,
        remaining_usage=remaining if status != "UNKNOWN" else None,
        lifetime_usage=lifetime_usage if status != "UNKNOWN" else None,
    )


def add_applicability_for_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    battery_id: uuid.UUID,
) -> MaintenanceRequirement:
    requirement = get_requirement(
        db, organization_id=organization_id, requirement_id=requirement_id
    )
    battery_service.get_battery(db, organization_id=organization_id, battery_id=battery_id)

    db.add(
        MaintenanceRequirementApplicability(
            organization_id=organization_id, requirement_id=requirement.id, battery_id=battery_id
        )
    )
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_requirement.applicability_added",
        entity_type="MaintenanceRequirement",
        entity_id=requirement.id,
        metadata={"battery_id": str(battery_id)},
    )
    db.commit()
    return requirement


def add_applicability_for_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    component_id: uuid.UUID,
) -> MaintenanceRequirement:
    requirement = get_requirement(
        db, organization_id=organization_id, requirement_id=requirement_id
    )
    component_service.get_component(db, organization_id=organization_id, component_id=component_id)

    db.add(
        MaintenanceRequirementApplicability(
            organization_id=organization_id,
            requirement_id=requirement.id,
            component_id=component_id,
        )
    )
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_requirement.applicability_added",
        entity_type="MaintenanceRequirement",
        entity_id=requirement.id,
        metadata={"component_id": str(component_id)},
    )
    db.commit()
    return requirement


def record_accomplishment_for_battery(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    battery_id: uuid.UUID,
    payload: AssetMaintenanceAccomplishmentCreateRequest,
) -> MaintenanceAccomplishment:
    get_requirement(db, organization_id=organization_id, requirement_id=requirement_id)
    battery_service.get_battery(db, organization_id=organization_id, battery_id=battery_id)

    accomplishment = MaintenanceAccomplishment(
        organization_id=organization_id,
        requirement_id=requirement_id,
        battery_id=battery_id,
        accomplished_at=payload.accomplished_at,
        work_order_id=payload.work_order_id,
        notes=payload.notes,
    )
    db.add(accomplishment)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_accomplishment.recorded",
        entity_type="MaintenanceAccomplishment",
        entity_id=accomplishment.id,
        metadata={"requirement_id": str(requirement_id), "battery_id": str(battery_id)},
    )
    db.commit()
    db.refresh(accomplishment)
    return accomplishment


def record_accomplishment_for_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    requirement_id: uuid.UUID,
    component_id: uuid.UUID,
    payload: AssetMaintenanceAccomplishmentCreateRequest,
) -> MaintenanceAccomplishment:
    get_requirement(db, organization_id=organization_id, requirement_id=requirement_id)
    component_service.get_component(db, organization_id=organization_id, component_id=component_id)

    accomplishment = MaintenanceAccomplishment(
        organization_id=organization_id,
        requirement_id=requirement_id,
        component_id=component_id,
        accomplished_at=payload.accomplished_at,
        work_order_id=payload.work_order_id,
        notes=payload.notes,
    )
    db.add(accomplishment)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="maintenance_accomplishment.recorded",
        entity_type="MaintenanceAccomplishment",
        entity_id=accomplishment.id,
        metadata={"requirement_id": str(requirement_id), "component_id": str(component_id)},
    )
    db.commit()
    db.refresh(accomplishment)
    return accomplishment


def get_maintenance_due_for_battery(
    db: Session, *, organization_id: uuid.UUID, battery_id: uuid.UUID
) -> list[MaintenanceDueItem]:
    battery = battery_service.get_battery(
        db, organization_id=organization_id, battery_id=battery_id
    )
    requirement_ids = (
        db.execute(
            select(MaintenanceRequirementApplicability.requirement_id).where(
                MaintenanceRequirementApplicability.organization_id == organization_id,
                MaintenanceRequirementApplicability.battery_id == battery_id,
            )
        )
        .scalars()
        .all()
    )
    items: list[MaintenanceDueItem] = []
    for requirement_id in requirement_ids:
        requirement = get_requirement(
            db, organization_id=organization_id, requirement_id=requirement_id
        )
        items.append(
            _evaluate_for_battery(
                db, organization_id=organization_id, battery=battery, requirement=requirement
            )
        )
    return items


def get_maintenance_due_for_component(
    db: Session, *, organization_id: uuid.UUID, component_id: uuid.UUID
) -> list[MaintenanceDueItem]:
    component = component_service.get_component(
        db, organization_id=organization_id, component_id=component_id
    )
    requirement_ids = (
        db.execute(
            select(MaintenanceRequirementApplicability.requirement_id).where(
                MaintenanceRequirementApplicability.organization_id == organization_id,
                MaintenanceRequirementApplicability.component_id == component_id,
            )
        )
        .scalars()
        .all()
    )
    items: list[MaintenanceDueItem] = []
    for requirement_id in requirement_ids:
        requirement = get_requirement(
            db, organization_id=organization_id, requirement_id=requirement_id
        )
        items.append(
            _evaluate_for_component(
                db, organization_id=organization_id, component=component, requirement=requirement
            )
        )
    return items
