import datetime
import uuid

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class RegulatoryAuthority:
    DGCA = "DGCA"
    FAA = "FAA"
    EASA = "EASA"
    CASA = "CASA"
    UK_CAA = "UK_CAA"
    OTHER = "OTHER"


class RegulatoryRequirement(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A single citable regulatory requirement. Deliberately NOT the full
    condition-tree/ApplicabilityRule engine the frontend prototype models
    (frontend/lib/mock/types.ts ApplicabilityCondition/ApplicabilityRule,
    with AND/OR/NOT combinators over aircraft-type/MSN-range/engine-type
    conditions) — that is a genuine rules-engine build, not a persistence
    slice, and is explicitly deferred rather than faked with a shallow
    placeholder. Applicability here is recorded directly on each
    ComplianceAssessment instead of evaluated from a rule tree.
    """

    __tablename__ = "regulatory_requirements"

    authority: Mapped[str] = mapped_column(String(16), nullable=False)
    regulatory_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulatory_documents.id"), nullable=True
    )
    requirement_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    effective_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    compliance_time: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class ComplianceAssessmentStatus:
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ComplianceAssessment(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "compliance_assessments"

    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False, index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regulatory_requirements.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ComplianceAssessmentStatus.UNKNOWN
    )
    evaluated_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    evaluated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A human can override a system/initial determination — recorded
    # explicitly rather than silently overwriting status with no trace.
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
