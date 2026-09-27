import datetime
import uuid
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    obligations = relationship("ComplianceObligation", back_populates="requirement")


class ComplianceAssessmentStatus:
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ComplianceState(StrEnum):
    """Deterministic compliance lifecycle states.
    
    Domain Invariants:
    - INSUFFICIENT_DATA must never silently become NOT_APPLICABLE.
    - REVIEW_REQUIRED must remain review-required until an authorized workflow resolves it.
    - COMPLIANT requires satisfied required actions and verified evidence.
    """

    NOT_EVALUATED = "NOT_EVALUATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    DUE = "DUE"
    OVERDUE = "OVERDUE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    BLOCKED = "BLOCKED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ComplianceObligation(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Authoritative compliance obligation linking a regulatory requirement to an asset/aircraft.
    
    Represents: 'Requirement X applies to Asset Y and must be satisfied.'
    Tracks applicability, due dates, required actions, evidence requirements, and completion/verification.
    """

    __tablename__ = "compliance_obligations"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regulatory_requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applicability_rules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("aircraft.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    applicability_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applicability_evaluations.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ComplianceState.NOT_EVALUATED.value,
        index=True,
    )
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM")
    due_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True, index=True)
    recurrence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    responsible_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    required_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_requirements: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    requirement = relationship("RegulatoryRequirement", back_populates="obligations")
    rule = relationship("ApplicabilityRule")
    applicability_evaluation = relationship("ApplicabilityEvaluation")
    evidence_items = relationship("Evidence", back_populates="obligation")
    assigned_user = relationship("User")
    findings = relationship("Finding", back_populates="compliance_obligation")
    inspection_requirements = relationship("InspectionRequirement", back_populates="compliance_obligation")


class ComplianceAssessment(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "compliance_assessments"

    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True
    )
    # Phase 1B / M1.5 compatibility mapping (migration 0031, 0038) -- supports
    # either aircraft_id (aircraft assessments) or asset_id (generic / drone asset assessments).
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
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

