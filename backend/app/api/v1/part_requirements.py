import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.part_requirement import (
    PartRequirementCreateRequest,
    PartRequirementResponse,
    PartRequirementUpdateRequest,
)
from app.services import part_requirement_service

router = APIRouter(prefix="/part-requirements", tags=["part-requirements"])


@router.post("", response_model=PartRequirementResponse, status_code=201)
def create_part_requirement(
    payload: PartRequirementCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> PartRequirementResponse:
    requirement = part_requirement_service.create_part_requirement(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return PartRequirementResponse.model_validate(requirement)


@router.get("/{requirement_id}", response_model=PartRequirementResponse)
def get_part_requirement(
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> PartRequirementResponse:
    requirement = part_requirement_service.get_part_requirement(
        db, organization_id=current_user.organization_id, requirement_id=requirement_id
    )
    return PartRequirementResponse.model_validate(requirement)


@router.get("/by-work-order/{work_order_id}", response_model=list[PartRequirementResponse])
def list_part_requirements_for_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> list[PartRequirementResponse]:
    requirements = part_requirement_service.list_part_requirements_for_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return [PartRequirementResponse.model_validate(r) for r in requirements]


@router.patch("/{requirement_id}", response_model=PartRequirementResponse)
def update_part_requirement(
    requirement_id: uuid.UUID,
    payload: PartRequirementUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> PartRequirementResponse:
    requirement = part_requirement_service.update_part_requirement(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        payload=payload,
    )
    return PartRequirementResponse.model_validate(requirement)
