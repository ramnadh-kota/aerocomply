"""Technician qualification domain: the smallest persistent model needed to
answer "can technician X perform task Y on aircraft Z?" with a real,
deterministic, non-fabricated answer.

Deliberately not a training/HR system: no course catalog, no certificate
documents, no renewal workflow. A TechnicianQualification is a real grant —
user_id qualified on aircraft_type, optionally time-bounded, revocable.

check_authorization never infers authorization from application role
(CAMO_MANAGER, MAINTENANCE_ENGINEER, etc.) — role governs what a user can do
in the system (RBAC), qualification governs what aircraft type they are
authorized to work on (an operational fact), and the two are intentionally
independent here, matching how a real MRO separates system permissions from
type-rating/qualification records.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.aircraft import Aircraft
from app.models.task import Task
from app.models.technician_qualification import TechnicianQualification
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.technician import (
    TechnicianAuthorizationResponse,
    TechnicianQualificationCreateRequest,
)
from app.services.audit_service import record_audit_event


def grant_qualification(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: TechnicianQualificationCreateRequest,
) -> TechnicianQualification:
    technician = db.execute(
        select(User).where(User.id == payload.user_id, User.organization_id == organization_id)
    ).scalar_one_or_none()
    if technician is None:
        raise NotFoundError("User not found in this organization")

    qualification = TechnicianQualification(
        organization_id=organization_id,
        user_id=payload.user_id,
        aircraft_type=payload.aircraft_type,
        qualification_type=payload.qualification_type,
        granted_at=payload.granted_at or datetime.now(UTC),
        expires_at=payload.expires_at,
        revoked=False,
        granted_by_user_id=actor_user_id,
    )
    db.add(qualification)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="technician_qualification.granted",
        entity_type="TechnicianQualification",
        entity_id=qualification.id,
        metadata={
            "technician_user_id": str(payload.user_id),
            "aircraft_type": payload.aircraft_type,
        },
    )
    db.commit()
    db.refresh(qualification)
    return qualification


def list_qualifications(
    db: Session, *, organization_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> list[TechnicianQualification]:
    stmt = select(TechnicianQualification).where(
        TechnicianQualification.organization_id == organization_id
    )
    if user_id is not None:
        stmt = stmt.where(TechnicianQualification.user_id == user_id)
    return list(db.execute(stmt).scalars().all())


def revoke_qualification(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    qualification_id: uuid.UUID,
) -> TechnicianQualification:
    qualification = db.execute(
        select(TechnicianQualification).where(
            TechnicianQualification.id == qualification_id,
            TechnicianQualification.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if qualification is None:
        raise NotFoundError("Technician qualification not found")
    qualification.revoked = True
    db.add(qualification)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="technician_qualification.revoked",
        entity_type="TechnicianQualification",
        entity_id=qualification.id,
        metadata={},
    )
    db.commit()
    db.refresh(qualification)
    return qualification


def assign_technician(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    task_id: uuid.UUID,
    technician_user_id: uuid.UUID,
) -> Task:
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Task not found")
    technician = db.execute(
        select(User).where(
            User.id == technician_user_id, User.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if technician is None:
        raise NotFoundError("Technician not found in this organization")

    task.assigned_technician_user_id = technician_user_id
    db.add(task)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="task.technician_assigned",
        entity_type="Task",
        entity_id=task.id,
        metadata={"technician_user_id": str(technician_user_id)},
    )
    db.commit()
    db.refresh(task)
    return task


def check_authorization(
    db: Session,
    *,
    organization_id: uuid.UUID,
    task_id: uuid.UUID,
    technician_user_id: uuid.UUID,
) -> TechnicianAuthorizationResponse:
    task = db.execute(
        select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
    ).scalar_one_or_none()
    if task is None:
        raise NotFoundError("Task not found")

    technician = db.execute(
        select(User).where(
            User.id == technician_user_id, User.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if technician is None:
        return TechnicianAuthorizationResponse(
            status="UNKNOWN",
            reason="Technician user not found in this organization.",
            task_id=task_id,
            technician_user_id=technician_user_id,
            aircraft_type=None,
            qualification_id=None,
        )

    work_order = db.execute(
        select(WorkOrder).where(WorkOrder.id == task.work_order_id)
    ).scalar_one_or_none()
    if work_order is None:
        return TechnicianAuthorizationResponse(
            status="UNKNOWN",
            reason="This task's work order could not be resolved.",
            task_id=task_id,
            technician_user_id=technician_user_id,
            aircraft_type=None,
            qualification_id=None,
        )

    aircraft = db.execute(
        select(Aircraft).where(Aircraft.id == work_order.aircraft_id)
    ).scalar_one_or_none()
    if aircraft is None:
        return TechnicianAuthorizationResponse(
            status="UNKNOWN",
            reason="This task's aircraft could not be resolved.",
            task_id=task_id,
            technician_user_id=technician_user_id,
            aircraft_type=None,
            qualification_id=None,
        )

    qualifications = list(
        db.execute(
            select(TechnicianQualification).where(
                TechnicianQualification.organization_id == organization_id,
                TechnicianQualification.user_id == technician_user_id,
                TechnicianQualification.aircraft_type == aircraft.aircraft_type,
            )
        )
        .scalars()
        .all()
    )

    if not qualifications:
        return TechnicianAuthorizationResponse(
            status="MISSING",
            reason=(
                f"No qualification record exists for this technician on aircraft type "
                f"{aircraft.aircraft_type!r}."
            ),
            task_id=task_id,
            technician_user_id=technician_user_id,
            aircraft_type=aircraft.aircraft_type,
            qualification_id=None,
        )

    now = datetime.now(UTC)
    active = [q for q in qualifications if not q.revoked]
    if not active:
        latest = max(qualifications, key=lambda q: q.granted_at)
        return TechnicianAuthorizationResponse(
            status="NOT_AUTHORIZED",
            reason=f"Qualification {latest.id} for {aircraft.aircraft_type!r} has been revoked.",
            task_id=task_id,
            technician_user_id=technician_user_id,
            aircraft_type=aircraft.aircraft_type,
            qualification_id=latest.id,
        )

    valid = [q for q in active if q.expires_at is None or q.expires_at > now]
    if valid:
        chosen = max(valid, key=lambda q: q.granted_at)
        return TechnicianAuthorizationResponse(
            status="AUTHORIZED",
            reason=(
                f"Qualification {chosen.id} ({chosen.qualification_type}) for "
                f"{aircraft.aircraft_type!r} is active."
            ),
            task_id=task_id,
            technician_user_id=technician_user_id,
            aircraft_type=aircraft.aircraft_type,
            qualification_id=chosen.id,
        )

    expired = max(active, key=lambda q: q.expires_at or q.granted_at)
    return TechnicianAuthorizationResponse(
        status="EXPIRED",
        reason=(
            f"Qualification {expired.id} for {aircraft.aircraft_type!r} "
            f"expired on {expired.expires_at}."
        ),
        task_id=task_id,
        technician_user_id=technician_user_id,
        aircraft_type=aircraft.aircraft_type,
        qualification_id=expired.id,
    )
