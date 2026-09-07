import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.errors import AeroComplyError
from app.core.permissions import Permission
from app.models.inspection_requirement import InspectionRequirementStatus
from app.schemas.auth import CurrentUser
from app.schemas.inspection import (
    InspectionRequirementCreateRequest,
    InspectionRequirementResponse,
    InspectionTransitionRequest,
)
from app.services import inspection_service

router = APIRouter(prefix="/inspections", tags=["inspections"])


@router.post("", response_model=InspectionRequirementResponse, status_code=201)
def create_inspection_requirement(
    payload: InspectionRequirementCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE)),
) -> InspectionRequirementResponse:
    # organization_id always comes from the authenticated user, never the request body.
    requirement = inspection_service.create_inspection_requirement(
        db,
        organization_id=current_user.organization_id,
        task_id=payload.task_id,
        work_order_id=payload.work_order_id,
        required=payload.required,
    )
    return InspectionRequirementResponse.model_validate(requirement)


@router.get("/{requirement_id}", response_model=InspectionRequirementResponse)
def get_inspection_requirement(
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_READ)),
) -> InspectionRequirementResponse:
    requirement = inspection_service.get_inspection_requirement(
        db, organization_id=current_user.organization_id, requirement_id=requirement_id
    )
    return InspectionRequirementResponse.model_validate(requirement)


@router.get("/by-work-order/{work_order_id}", response_model=list[InspectionRequirementResponse])
def list_inspection_requirements_for_work_order(
    work_order_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_READ)),
) -> list[InspectionRequirementResponse]:
    requirements = inspection_service.list_inspection_requirements_for_work_order(
        db, organization_id=current_user.organization_id, work_order_id=work_order_id
    )
    return [InspectionRequirementResponse.model_validate(r) for r in requirements]


@router.post("/{requirement_id}/transition", response_model=InspectionRequirementResponse)
def transition_inspection_requirement(
    requirement_id: uuid.UUID,
    payload: InspectionTransitionRequest,
    db: Session = Depends(get_db_session),
    # There is no distinct "sign-off" permission in the catalog (see
    # app/core/permissions.py); INSPECTION_WRITE covers both creating a
    # requirement and performing its transitions (including RII completion),
    # mirroring EVIDENCE_WRITE's single-permission shape. The RII
    # independence rule itself is enforced in inspection_service regardless
    # of who holds this grant.
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE)),
) -> InspectionRequirementResponse:
    requirement = inspection_service.get_inspection_requirement(
        db, organization_id=current_user.organization_id, requirement_id=requirement_id
    )
    try:
        target_status = InspectionRequirementStatus(payload.target_status)
    except ValueError as exc:
        raise AeroComplyError(
            f"Invalid inspection requirement status: {payload.target_status}",
            code="invalid_status",
        ) from exc

    requirement = inspection_service.transition_inspection_requirement(
        db,
        requirement,
        target_status,
        actor_user_id=current_user.id,
        inspector_user_id=payload.inspector_user_id,
        rejection_reason=payload.rejection_reason,
    )
    return InspectionRequirementResponse.model_validate(requirement)
