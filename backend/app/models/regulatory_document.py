import datetime

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class RegulatoryDocumentType:
    AD = "AD"
    SB = "SB"
    REGULATION = "REGULATION"
    RULE = "RULE"
    AMC = "AMC"
    GM = "GM"
    SIB = "SIB"
    NOTICE = "NOTICE"
    OTHER = "OTHER"


class RegulatoryDocumentSourceStatus:
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"
    WITHDRAWN = "WITHDRAWN"


class RegulatoryDocument(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A regulatory publication (AD/SB/regulation/etc.) that a
    RegulatoryRequirement (M3.12) can cite via regulatory_document_id.

    Entered manually in this slice — there is no live authority feed
    (DGCA/FAA/EASA/CASA/UK CAA) configured anywhere in this codebase.
    sync_status is always NOT_CONFIGURED as a result; it exists as a real
    column (not a hardcoded API response) so that wiring in an actual
    provider later only requires writing to this column, not changing the
    schema. See regulatory_service.get_provider_status for the explicit
    truthful status this system reports today.
    """

    __tablename__ = "regulatory_documents"

    authority: Mapped[str] = mapped_column(String(16), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    doc_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publication_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    source_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RegulatoryDocumentSourceStatus.PUBLISHED
    )
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sync_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_CONFIGURED"
    )
