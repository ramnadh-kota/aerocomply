import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.part import PartCreateRequest, PartResponse, PartUpdateRequest
from app.services import part_service

router = APIRouter(prefix="/parts", tags=["parts"])


@router.post("", response_model=PartResponse, status_code=201)
def create_part(
    payload: PartCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> PartResponse:
    # organization_id always comes from the authenticated user, never the request body.
    part = part_service.create_part(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return PartResponse.model_validate(part)


@router.get("", response_model=list[PartResponse])
def list_parts(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> list[PartResponse]:
    parts = part_service.list_parts(db, organization_id=current_user.organization_id)
    return [PartResponse.model_validate(p) for p in parts]


@router.get("/{part_id}", response_model=PartResponse)
def get_part(
    part_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> PartResponse:
    part = part_service.get_part(
        db, organization_id=current_user.organization_id, part_id=part_id
    )
    return PartResponse.model_validate(part)


@router.patch("/{part_id}", response_model=PartResponse)
def update_part(
    part_id: uuid.UUID,
    payload: PartUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> PartResponse:
    part = part_service.update_part(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        payload=payload,
    )
    return PartResponse.model_validate(part)
