import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.aog_event import (
    AogBlockerCreateRequest,
    AogEventCreateRequest,
    AogEventResponse,
    AogEventUpdateRequest,
)
from app.schemas.auth import CurrentUser
from app.services import aog_service

router = APIRouter(prefix="/aog-events", tags=["aog"])


@router.post("", response_model=AogEventResponse, status_code=201)
def declare_aog(
    payload: AogEventCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.declare_aog(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return AogEventResponse.model_validate(event)


@router.get("", response_model=list[AogEventResponse])
def list_aog_events(
    status: str | None = None,
    aircraft_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[AogEventResponse]:
    events = aog_service.list_aog_events(
        db, organization_id=current_user.organization_id, status=status, aircraft_id=aircraft_id
    )
    return [AogEventResponse.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=AogEventResponse)
def get_aog_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AogEventResponse:
    event = aog_service.get_aog_event(
        db, organization_id=current_user.organization_id, event_id=event_id
    )
    return AogEventResponse.model_validate(event)


@router.patch("/{event_id}", response_model=AogEventResponse)
def update_aog_event(
    event_id: uuid.UUID,
    payload: AogEventUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.update_aog_event(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        event_id=event_id,
        payload=payload,
    )
    return AogEventResponse.model_validate(event)


@router.post("/{event_id}/blockers", response_model=AogEventResponse, status_code=201)
def add_blocker(
    event_id: uuid.UUID,
    payload: AogBlockerCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.add_blocker(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        event_id=event_id,
        payload=payload,
    )
    return AogEventResponse.model_validate(event)


@router.post("/{event_id}/blockers/{blocker_id}/resolve", response_model=AogEventResponse)
def resolve_blocker(
    event_id: uuid.UUID,
    blocker_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.resolve_blocker(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        event_id=event_id,
        blocker_id=blocker_id,
    )
    return AogEventResponse.model_validate(event)


@router.post("/{event_id}/start-recovery", response_model=AogEventResponse)
def start_recovery(
    event_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.start_recovery(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        event_id=event_id,
    )
    return AogEventResponse.model_validate(event)


@router.post("/{event_id}/mark-recovered", response_model=AogEventResponse)
def mark_recovered(
    event_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.mark_recovered(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        event_id=event_id,
    )
    return AogEventResponse.model_validate(event)


@router.post("/{event_id}/cancel", response_model=AogEventResponse)
def cancel_aog_event(
    event_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AogEventResponse:
    event = aog_service.cancel_aog_event(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        event_id=event_id,
    )
    return AogEventResponse.model_validate(event)
