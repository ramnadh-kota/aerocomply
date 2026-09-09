import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.regulatory_document import (
    RegulatoryDocumentCreateRequest,
    RegulatoryDocumentResponse,
    RegulatoryProviderStatus,
)
from app.services import regulatory_service

router = APIRouter(prefix="/regulatory-documents", tags=["regulatory"])


@router.post("", response_model=RegulatoryDocumentResponse, status_code=201)
def create_document(
    payload: RegulatoryDocumentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_WRITE)),
) -> RegulatoryDocumentResponse:
    document = regulatory_service.create_document(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return RegulatoryDocumentResponse.model_validate(document)


@router.get("", response_model=list[RegulatoryDocumentResponse])
def list_documents(
    authority: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_READ)),
) -> list[RegulatoryDocumentResponse]:
    documents = regulatory_service.list_documents(
        db, organization_id=current_user.organization_id, authority=authority
    )
    return [RegulatoryDocumentResponse.model_validate(d) for d in documents]


@router.get("/provider-status/all", response_model=list[RegulatoryProviderStatus])
def get_provider_status(
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_READ)),
) -> list[RegulatoryProviderStatus]:
    return regulatory_service.get_provider_status()


@router.get("/{document_id}", response_model=RegulatoryDocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.REGULATION_READ)),
) -> RegulatoryDocumentResponse:
    document = regulatory_service.get_document(
        db, organization_id=current_user.organization_id, document_id=document_id
    )
    return RegulatoryDocumentResponse.model_validate(document)
