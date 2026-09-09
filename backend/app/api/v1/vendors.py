import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.vendor import VendorCreateRequest, VendorResponse, VendorUpdateRequest
from app.services import vendor_service

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.post("", response_model=VendorResponse, status_code=201)
def create_vendor(
    payload: VendorCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_WRITE)),
) -> VendorResponse:
    # organization_id always comes from the authenticated user, never the request body.
    vendor = vendor_service.create_vendor(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return VendorResponse.model_validate(vendor)


@router.get("", response_model=list[VendorResponse])
def list_vendors(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_READ)),
) -> list[VendorResponse]:
    vendors = vendor_service.list_vendors(db, organization_id=current_user.organization_id)
    return [VendorResponse.model_validate(v) for v in vendors]


@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(
    vendor_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_READ)),
) -> VendorResponse:
    vendor = vendor_service.get_vendor(
        db, organization_id=current_user.organization_id, vendor_id=vendor_id
    )
    return VendorResponse.model_validate(vendor)


@router.patch("/{vendor_id}", response_model=VendorResponse)
def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.VENDOR_WRITE)),
) -> VendorResponse:
    vendor = vendor_service.update_vendor(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        vendor_id=vendor_id,
        payload=payload,
    )
    return VendorResponse.model_validate(vendor)
