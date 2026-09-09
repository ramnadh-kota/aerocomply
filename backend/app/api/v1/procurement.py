import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestClarifyRequest,
    ProcurementRequestCreateRequest,
    ProcurementRequestRejectRequest,
    ProcurementRequestResponse,
)
from app.services import procurement_service

router = APIRouter(prefix="/procurement-requests", tags=["procurement"])


@router.post("", response_model=ProcurementRequestResponse, status_code=201)
def create_request(
    payload: ProcurementRequestCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> ProcurementRequestResponse:
    request = procurement_service.create_request(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.get("", response_model=list[ProcurementRequestResponse])
def list_requests(
    status: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_READ)),
) -> list[ProcurementRequestResponse]:
    requests = procurement_service.list_requests(
        db, organization_id=current_user.organization_id, status=status
    )
    return [ProcurementRequestResponse.model_validate(r) for r in requests]


@router.get("/{request_id}", response_model=ProcurementRequestResponse)
def get_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_READ)),
) -> ProcurementRequestResponse:
    request = procurement_service.get_request(
        db, organization_id=current_user.organization_id, request_id=request_id
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/submit-for-review", response_model=ProcurementRequestResponse)
def submit_for_review(
    request_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> ProcurementRequestResponse:
    request = procurement_service.submit_for_review(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/approve", response_model=ProcurementRequestResponse)
def approve_request(
    request_id: uuid.UUID,
    payload: ProcurementRequestApproveRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_APPROVE)),
) -> ProcurementRequestResponse:
    request = procurement_service.approve_request(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
        payload=payload,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/reject", response_model=ProcurementRequestResponse)
def reject_request(
    request_id: uuid.UUID,
    payload: ProcurementRequestRejectRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_APPROVE)),
) -> ProcurementRequestResponse:
    request = procurement_service.reject_request(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
        payload=payload,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/request-clarification", response_model=ProcurementRequestResponse)
def request_clarification(
    request_id: uuid.UUID,
    payload: ProcurementRequestClarifyRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_APPROVE)),
) -> ProcurementRequestResponse:
    request = procurement_service.request_clarification(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
        payload=payload,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/resubmit", response_model=ProcurementRequestResponse)
def resubmit_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> ProcurementRequestResponse:
    request = procurement_service.resubmit_request(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/mark-ordered", response_model=ProcurementRequestResponse)
def mark_ordered(
    request_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> ProcurementRequestResponse:
    request = procurement_service.mark_ordered(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/mark-received", response_model=ProcurementRequestResponse)
def mark_received(
    request_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> ProcurementRequestResponse:
    request = procurement_service.mark_received(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
    )
    return ProcurementRequestResponse.model_validate(request)


@router.post("/{request_id}/close", response_model=ProcurementRequestResponse)
def close_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> ProcurementRequestResponse:
    request = procurement_service.close_request(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        request_id=request_id,
    )
    return ProcurementRequestResponse.model_validate(request)
