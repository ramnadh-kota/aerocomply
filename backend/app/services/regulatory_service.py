import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.compliance import RegulatoryAuthority
from app.models.regulatory_document import RegulatoryDocument
from app.schemas.regulatory_document import (
    RegulatoryDocumentCreateRequest,
    RegulatoryProviderStatus,
)
from app.services.audit_service import record_audit_event

# Every authority reports NOT_CONFIGURED — there is no DGCA/FAA/EASA/CASA/UK
# CAA feed integration anywhere in this codebase. A real provider.py adapter
# for a given authority is what would flip a single authority's row here to
# a live-sync status; nothing about the app pretends otherwise in the
# meantime (see app/models/regulatory_document.py for the same rule on
# RegulatoryDocument.sync_status).
_KNOWN_AUTHORITIES = [
    RegulatoryAuthority.DGCA,
    RegulatoryAuthority.FAA,
    RegulatoryAuthority.EASA,
    RegulatoryAuthority.CASA,
    RegulatoryAuthority.UK_CAA,
]


def create_document(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: RegulatoryDocumentCreateRequest,
) -> RegulatoryDocument:
    document = RegulatoryDocument(
        organization_id=organization_id,
        authority=payload.authority,
        doc_type=payload.doc_type,
        doc_number=payload.doc_number,
        title=payload.title,
        revision=payload.revision,
        publication_date=payload.publication_date,
        effective_date=payload.effective_date,
        source_status=payload.source_status,
        source_url=payload.source_url,
    )
    db.add(document)
    db.flush()
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="regulatory_document.created",
        entity_type="RegulatoryDocument",
        entity_id=document.id,
        metadata={"doc_number": payload.doc_number},
    )
    db.commit()
    db.refresh(document)
    return document


def get_document(
    db: Session, *, organization_id: uuid.UUID, document_id: uuid.UUID
) -> RegulatoryDocument:
    document = db.execute(
        select(RegulatoryDocument).where(
            RegulatoryDocument.id == document_id,
            RegulatoryDocument.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if document is None:
        raise NotFoundError("Regulatory document not found")
    return document


def list_documents(
    db: Session, *, organization_id: uuid.UUID, authority: str | None = None
) -> list[RegulatoryDocument]:
    stmt = select(RegulatoryDocument).where(RegulatoryDocument.organization_id == organization_id)
    if authority is not None:
        stmt = stmt.where(RegulatoryDocument.authority == authority)
    return list(db.execute(stmt).scalars().all())


def get_provider_status() -> list[RegulatoryProviderStatus]:
    return [
        RegulatoryProviderStatus(
            authority=authority,
            status="NOT_CONFIGURED",
            reason=(
                f"No live {authority} regulatory feed is configured. "
                "Documents must be entered manually until a provider adapter "
                "is implemented and connected."
            ),
        )
        for authority in _KNOWN_AUTHORITIES
    ]
