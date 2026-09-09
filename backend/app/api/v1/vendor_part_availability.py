import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.vendor_part_availability import (
    VendorFitResult,
    VendorPartAvailabilityCreateRequest,
    VendorPartAvailabilityResponse,
    VendorPartAvailabilityUpdateRequest,
)
from app.services import vendor_fit_service, vendor_part_availability_service

router = APIRouter(tags=["vendor-part-availability"])


@router.post(
    "/vendor-part-availability", response_model=VendorPartAvailabilityResponse, status_code=201
)
def create_availability(
    payload: VendorPartAvailabilityCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_WRITE)),
) -> VendorPartAvailabilityResponse:
    availability = vendor_part_availability_service.create_availability(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return VendorPartAvailabilityResponse.model_validate(availability)


@router.patch(
    "/vendor-part-availability/{availability_id}", response_model=VendorPartAvailabilityResponse
)
def update_availability(
    availability_id: uuid.UUID,
    payload: VendorPartAvailabilityUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_WRITE)),
) -> VendorPartAvailabilityResponse:
    availability = vendor_part_availability_service.update_availability(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        availability_id=availability_id,
        payload=payload,
    )
    return VendorPartAvailabilityResponse.model_validate(availability)


@router.get(
    "/parts/{part_id}/vendor-availability", response_model=list[VendorPartAvailabilityResponse]
)
def list_availability_for_part(
    part_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_READ)),
) -> list[VendorPartAvailabilityResponse]:
    lines = vendor_part_availability_service.list_availability_for_part(
        db, organization_id=current_user.organization_id, part_id=part_id
    )
    return [VendorPartAvailabilityResponse.model_validate(line) for line in lines]


@router.get("/parts/{part_id}/vendor-fit", response_model=list[VendorFitResult])
def get_vendor_fit(
    part_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_READ)),
) -> list[VendorFitResult]:
    return vendor_fit_service.score_vendor_options_for_part(
        db, organization_id=current_user.organization_id, part_id=part_id
    )
