import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.errors import AeroComplyError
from app.core.permissions import Permission
from app.models.evidence import EvidenceStatus
from app.schemas.auth import CurrentUser
from app.schemas.evidence import (
    EvidenceCreateRequest,
    EvidenceResponse,
    EvidenceTransitionRequest,
)
from app.services import evidence_service

router = APIRouter(prefix="/evidence", tags=["evidence"])


@router.post("", response_model=EvidenceResponse, status_code=201)
def create_evidence(
    payload: EvidenceCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_WRITE)),
) -> EvidenceResponse:
    # organization_id always comes from the authenticated user, never the request body.
    evidence = evidence_service.create_evidence(
        db,
        organization_id=current_user.organization_id,
        task_id=payload.task_id,
        uploaded_by_user_id=current_user.id,
    )
    return EvidenceResponse.model_validate(evidence)


@router.get("/{evidence_id}", response_model=EvidenceResponse)
def get_evidence(
    evidence_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_READ)),
) -> EvidenceResponse:
    evidence = evidence_service.get_evidence(
        db, organization_id=current_user.organization_id, evidence_id=evidence_id
    )
    return EvidenceResponse.model_validate(evidence)


@router.post("/{evidence_id}/transition", response_model=EvidenceResponse)
def transition_evidence(
    evidence_id: uuid.UUID,
    payload: EvidenceTransitionRequest,
    db: Session = Depends(get_db_session),
    # There is no distinct EVIDENCE_REVIEW permission in the permission catalog
    # (see app/core/permissions.py); EVIDENCE_WRITE ("evidence:upload") is the
    # only write-side evidence permission today and covers both upload-side
    # (UPLOADED/SUBMITTED) and reviewer-side (ACCEPTED/REJECTED) transitions.
    current_user: CurrentUser = Depends(require_permission(Permission.EVIDENCE_WRITE)),
) -> EvidenceResponse:
    evidence = evidence_service.get_evidence(
        db, organization_id=current_user.organization_id, evidence_id=evidence_id
    )
    try:
        target_status = EvidenceStatus(payload.target_status)
    except ValueError as exc:
        raise AeroComplyError(
            f"Invalid evidence status: {payload.target_status}", code="invalid_status"
        ) from exc

    evidence = evidence_service.transition_evidence(
        db,
        evidence,
        target_status,
        actor_user_id=current_user.id,
        rejection_reason=payload.rejection_reason,
    )
    return EvidenceResponse.model_validate(evidence)
