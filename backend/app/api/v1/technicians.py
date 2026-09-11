import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.task import TaskResponse
from app.schemas.technician import (
    AssignTechnicianRequest,
    TechnicianAuthorizationResponse,
    TechnicianQualificationCreateRequest,
    TechnicianQualificationResponse,
)
from app.services import technician_service

router = APIRouter(tags=["technicians"])


@router.post(
    "/technician-qualifications", response_model=TechnicianQualificationResponse, status_code=201
)
def grant_qualification(
    payload: TechnicianQualificationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.TECHNICIAN_WRITE)),
) -> TechnicianQualificationResponse:
    qualification = technician_service.grant_qualification(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return TechnicianQualificationResponse.model_validate(qualification)


@router.get("/technician-qualifications", response_model=list[TechnicianQualificationResponse])
def list_qualifications(
    user_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.TECHNICIAN_READ)),
) -> list[TechnicianQualificationResponse]:
    qualifications = technician_service.list_qualifications(
        db, organization_id=current_user.organization_id, user_id=user_id
    )
    return [TechnicianQualificationResponse.model_validate(q) for q in qualifications]


@router.post(
    "/technician-qualifications/{qualification_id}/revoke",
    response_model=TechnicianQualificationResponse,
)
def revoke_qualification(
    qualification_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.TECHNICIAN_WRITE)),
) -> TechnicianQualificationResponse:
    qualification = technician_service.revoke_qualification(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        qualification_id=qualification_id,
    )
    return TechnicianQualificationResponse.model_validate(qualification)


@router.post("/tasks/{task_id}/assign-technician", response_model=TaskResponse)
def assign_technician(
    task_id: uuid.UUID,
    payload: AssignTechnicianRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.TECHNICIAN_WRITE)),
) -> TaskResponse:
    task = technician_service.assign_technician(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        task_id=task_id,
        technician_user_id=payload.technician_user_id,
    )
    return TaskResponse.model_validate(task)


@router.get(
    "/tasks/{task_id}/technician-authorization/{technician_user_id}",
    response_model=TechnicianAuthorizationResponse,
)
def check_authorization(
    task_id: uuid.UUID,
    technician_user_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.TECHNICIAN_READ)),
) -> TechnicianAuthorizationResponse:
    return technician_service.check_authorization(
        db,
        organization_id=current_user.organization_id,
        task_id=task_id,
        technician_user_id=technician_user_id,
    )
