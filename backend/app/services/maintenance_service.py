import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.maintenance_requirement import (
    MaintenanceAccomplishment,
    MaintenanceIntervalType,
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)
from app.schemas.maintenance_requirement import (
    MaintenanceAccomplishmentCreateRequest,
    MaintenanceApplicabilityCreateRequest,
    MaintenanceDueItem,
    MaintenanceRequirementCreateRequest,
    MaintenanceRequirementResponse,
)
from app.services import aircraft_service
from app.services.audit_service import record_audit_event

# A calendar-interval requirement is DUE_SOON inside this window — matches the
# 30-day horizon convention already used for TAT AT_RISK elsewhere in this
# codebase (see tat_service's documented threshold), kept consistent rather
# than inventing a different number for maintenance.
_DUE_SOON_WINDOW_DAYS = 30


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


def list_requirements(
    db: Session, *, organization_id: uuid.UUID
) -> list[MaintenanceRequirement]:
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
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    applicability = MaintenanceRequirementApplicability(
        organization_id=organization_id,
        requirement_id=requirement.id,
        aircraft_id=payload.aircraft_id,
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
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    accomplishment = MaintenanceAccomplishment(
        organization_id=organization_id,
        requirement_id=requirement_id,
        aircraft_id=payload.aircraft_id,
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
    return db.execute(
        select(MaintenanceAccomplishment)
        .where(
            MaintenanceAccomplishment.organization_id == organization_id,
            MaintenanceAccomplishment.requirement_id == requirement_id,
            MaintenanceAccomplishment.aircraft_id == aircraft_id,
        )
        .order_by(MaintenanceAccomplishment.accomplished_at.desc())
    ).scalars().first()


def _due_status_for(
    requirement: MaintenanceRequirement, last_accomplished_at: datetime.date | None
) -> tuple[str, datetime.date | None, str]:
    if requirement.interval_type in (
        MaintenanceIntervalType.FLIGHT_HOURS,
        MaintenanceIntervalType.FLIGHT_CYCLES,
    ):
        # Honest limitation, not a gap silently filled in: this codebase does
        # not track aircraft flight-hour/flight-cycle utilization anywhere
        # yet, so a usage-based interval can never be computed here.
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

    due_date = last_accomplished_at + datetime.timedelta(
        days=requirement.calendar_interval_days
    )
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

    applicable_requirement_ids = db.execute(
        select(MaintenanceRequirementApplicability.requirement_id).where(
            MaintenanceRequirementApplicability.organization_id == organization_id,
            MaintenanceRequirementApplicability.aircraft_id == aircraft_id,
        )
    ).scalars().all()

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
