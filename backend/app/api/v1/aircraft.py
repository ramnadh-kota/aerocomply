import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.aircraft import AircraftCreateRequest, AircraftResponse
from app.schemas.auth import CurrentUser
from app.services import aircraft_service

router = APIRouter(prefix="/aircraft", tags=["aircraft"])


@router.post("", response_model=AircraftResponse, status_code=201)
def create_aircraft(
    payload: AircraftCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> AircraftResponse:
    # organization_id always comes from the authenticated user, never the request body.
    aircraft = aircraft_service.create_aircraft(
        db, organization_id=current_user.organization_id, payload=payload
    )
    return AircraftResponse.model_validate(aircraft)


@router.get("", response_model=list[AircraftResponse])
def list_aircraft(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[AircraftResponse]:
    aircraft = aircraft_service.list_aircraft(db, organization_id=current_user.organization_id)
    return [AircraftResponse.model_validate(a) for a in aircraft]


@router.get("/{aircraft_id}", response_model=AircraftResponse)
def get_aircraft(
    aircraft_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AircraftResponse:
    aircraft = aircraft_service.get_aircraft(
        db, organization_id=current_user.organization_id, aircraft_id=aircraft_id
    )
    return AircraftResponse.model_validate(aircraft)
