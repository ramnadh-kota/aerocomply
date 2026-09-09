import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.aog_event import AogBlocker, AogEvent, AogEventStatus
from app.schemas.aog_event import (
    AogBlockerCreateRequest,
    AogEventCreateRequest,
    AogEventUpdateRequest,
)
from app.services import aircraft_service
from app.services.audit_service import record_audit_event

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    AogEventStatus.DECLARED: {AogEventStatus.IN_RECOVERY, AogEventStatus.CANCELLED},
    AogEventStatus.IN_RECOVERY: {AogEventStatus.RECOVERED, AogEventStatus.CANCELLED},
}


def _require_transition(current: str, target: str) -> None:
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ConflictError(
            f"Cannot transition AOG event from {current} to {target}", code="invalid_transition"
        )


def declare_aog(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: AogEventCreateRequest,
) -> AogEvent:
    aircraft_service.get_aircraft(
        db, organization_id=organization_id, aircraft_id=payload.aircraft_id
    )
    event = AogEvent(
        organization_id=organization_id,
        aircraft_id=payload.aircraft_id,
        work_order_id=payload.work_order_id,
        status=AogEventStatus.DECLARED,
        severity=payload.severity,
        root_cause=payload.root_cause,
        declared_by_user_id=actor_user_id,
    )
    db.add(event)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="aog_event.declared",
        entity_type="AogEvent",
        entity_id=event.id,
        metadata={"aircraft_id": str(payload.aircraft_id), "severity": payload.severity},
    )
    db.commit()
    db.refresh(event)
    return event


def get_aog_event(
    db: Session, *, organization_id: uuid.UUID, event_id: uuid.UUID
) -> AogEvent:
    event = db.execute(
        select(AogEvent)
        .options(selectinload(AogEvent.blockers))
        .where(AogEvent.id == event_id, AogEvent.organization_id == organization_id)
    ).scalar_one_or_none()
    if event is None:
        raise NotFoundError("AOG event not found")
    return event


def list_aog_events(
    db: Session,
    *,
    organization_id: uuid.UUID,
    status: str | None = None,
    aircraft_id: uuid.UUID | None = None,
) -> list[AogEvent]:
    stmt = (
        select(AogEvent)
        .options(selectinload(AogEvent.blockers))
        .where(AogEvent.organization_id == organization_id)
    )
    if status is not None:
        stmt = stmt.where(AogEvent.status == status)
    if aircraft_id is not None:
        stmt = stmt.where(AogEvent.aircraft_id == aircraft_id)
    return list(db.execute(stmt).scalars().all())


def update_aog_event(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    event_id: uuid.UUID,
    payload: AogEventUpdateRequest,
) -> AogEvent:
    event = get_aog_event(db, organization_id=organization_id, event_id=event_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(event, field, value)
    db.add(event)
    if updates:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="aog_event.updated",
            entity_type="AogEvent",
            entity_id=event.id,
            metadata=updates,
        )
    db.commit()
    db.refresh(event)
    return event


def add_blocker(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    event_id: uuid.UUID,
    payload: AogBlockerCreateRequest,
) -> AogEvent:
    event = get_aog_event(db, organization_id=organization_id, event_id=event_id)
    blocker = AogBlocker(
        organization_id=organization_id,
        aog_event_id=event.id,
        blocker_type=payload.blocker_type,
        description=payload.description,
        source_reference=payload.source_reference,
    )
    db.add(blocker)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="aog_blocker.added",
        entity_type="AogBlocker",
        entity_id=blocker.id,
        metadata={"aog_event_id": str(event.id), "blocker_type": payload.blocker_type},
    )
    db.commit()
    db.refresh(event)
    return event


def resolve_blocker(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    event_id: uuid.UUID,
    blocker_id: uuid.UUID,
) -> AogEvent:
    event = get_aog_event(db, organization_id=organization_id, event_id=event_id)
    blocker = next((b for b in event.blockers if b.id == blocker_id), None)
    if blocker is None:
        raise NotFoundError("AOG blocker not found on this event")
    blocker.resolved = True
    db.add(blocker)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="aog_blocker.resolved",
        entity_type="AogBlocker",
        entity_id=blocker.id,
        metadata={"aog_event_id": str(event.id)},
    )
    db.commit()
    db.refresh(event)
    return event


def _transition(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    event: AogEvent,
    target_status: str,
    action: str,
) -> AogEvent:
    _require_transition(event.status, target_status)
    previous = event.status
    event.status = target_status
    db.add(event)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action=action,
        entity_type="AogEvent",
        entity_id=event.id,
        metadata={"from_status": previous, "to_status": target_status},
    )
    db.commit()
    db.refresh(event)
    return event


def start_recovery(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, event_id: uuid.UUID
) -> AogEvent:
    event = get_aog_event(db, organization_id=organization_id, event_id=event_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        event=event,
        target_status=AogEventStatus.IN_RECOVERY,
        action="aog_event.recovery_started",
    )


def mark_recovered(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, event_id: uuid.UUID
) -> AogEvent:
    event = get_aog_event(db, organization_id=organization_id, event_id=event_id)
    unresolved = [b for b in event.blockers if not b.resolved]
    if unresolved:
        raise ConflictError(
            "Cannot mark an AOG event recovered while unresolved blockers remain",
            code="unresolved_blockers",
        )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        event=event,
        target_status=AogEventStatus.RECOVERED,
        action="aog_event.recovered",
    )


def cancel_aog_event(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, event_id: uuid.UUID
) -> AogEvent:
    event = get_aog_event(db, organization_id=organization_id, event_id=event_id)
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        event=event,
        target_status=AogEventStatus.CANCELLED,
        action="aog_event.cancelled",
    )
