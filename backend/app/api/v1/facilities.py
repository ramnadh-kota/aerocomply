import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.facility import FacilityCreateRequest, FacilityResponse, FacilityUpdateRequest
from app.services import facility_service

router = APIRouter(tags=["facilities"])


@router.get("/facilities", response_model=list[FacilityResponse])
def list_facilities(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.FACILITY_READ)),
) -> list[FacilityResponse]:
    facilities = facility_service.list_facilities(db, organization_id=current_user.organization_id)
    return [FacilityResponse.model_validate(f) for f in facilities]


@router.post("/facilities", response_model=FacilityResponse, status_code=201)
def create_facility(
    payload: FacilityCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.FACILITY_WRITE)),
) -> FacilityResponse:
    facility = facility_service.create_facility(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return FacilityResponse.model_validate(facility)


@router.get("/facilities/{facility_id}", response_model=FacilityResponse)
def get_facility(
    facility_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.FACILITY_READ)),
) -> FacilityResponse:
    facility = facility_service.get_facility(
        db, organization_id=current_user.organization_id, facility_id=facility_id
    )
    return FacilityResponse.model_validate(facility)


@router.patch("/facilities/{facility_id}", response_model=FacilityResponse)
def update_facility(
    facility_id: uuid.UUID,
    payload: FacilityUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.FACILITY_WRITE)),
) -> FacilityResponse:
    facility = facility_service.update_facility(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        facility_id=facility_id,
        payload=payload,
    )
    return FacilityResponse.model_validate(facility)
