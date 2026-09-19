import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.finding import (
    FindingCreateRequest,
    FindingDispositionRequest,
    FindingResponse,
)
from app.services import finding_service

router = APIRouter(prefix="/findings", tags=["findings"])


@router.post("", response_model=FindingResponse, status_code=201)
def create_finding(
    payload: FindingCreateRequest,
    db: Session = Depends(get_db_session),
    # Reuses INSPECTION_WRITE (no dedicated "finding" permission exists yet;
    # a general finding is raised during the same inspection/maintenance
    # workflows that permission already gates -- see app/core/permissions.py
    # for the established precedent of not adding a narrower permission
    # unless the existing catalog genuinely has no fit).
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE)),
) -> FindingResponse:
    # organization_id always comes from the authenticated user, never the request body.
    finding = finding_service.create_finding(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        aircraft_id=payload.aircraft_id,
        asset_id=payload.asset_id,
        component_id=payload.component_id,
        inspection_requirement_id=payload.inspection_requirement_id,
        work_order_id=payload.work_order_id,
        task_id=payload.task_id,
        responsible_user_id=payload.responsible_user_id,
    )
    return FindingResponse.model_validate(finding)


@router.get("", response_model=list[FindingResponse])
def list_findings(
    aircraft_id: uuid.UUID | None = Query(default=None),
    asset_id: uuid.UUID | None = Query(default=None),
    work_order_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_READ)),
) -> list[FindingResponse]:
    findings = finding_service.list_findings(
        db,
        organization_id=current_user.organization_id,
        aircraft_id=aircraft_id,
        asset_id=asset_id,
        work_order_id=work_order_id,
        status=status,
    )
    return [FindingResponse.model_validate(f) for f in findings]


@router.get("/{finding_id}", response_model=FindingResponse)
def get_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_READ)),
) -> FindingResponse:
    finding = finding_service.get_finding(
        db, organization_id=current_user.organization_id, finding_id=finding_id
    )
    return FindingResponse.model_validate(finding)


@router.post("/{finding_id}/dispositions", response_model=FindingResponse)
def add_disposition(
    finding_id: uuid.UUID,
    payload: FindingDispositionRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE)),
) -> FindingResponse:
    finding = finding_service.get_finding(
        db, organization_id=current_user.organization_id, finding_id=finding_id
    )
    finding = finding_service.add_disposition(
        db,
        finding,
        actor_user_id=current_user.id,
        disposition_type=payload.disposition_type,
        corrective_action=payload.corrective_action,
        evidence_id=payload.evidence_id,
    )
    return FindingResponse.model_validate(finding)


@router.post("/{finding_id}/close", response_model=FindingResponse)
def close_finding(
    finding_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.INSPECTION_WRITE)),
) -> FindingResponse:
    finding = finding_service.get_finding(
        db, organization_id=current_user.organization_id, finding_id=finding_id
    )
    finding = finding_service.close_finding(db, finding, actor_user_id=current_user.id)
    return FindingResponse.model_validate(finding)
