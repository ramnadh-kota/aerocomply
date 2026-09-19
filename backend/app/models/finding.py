"""General-purpose Finding/Disposition domain model.

Distinct from `AssessmentFinding` (app/models/assessment.py), which is
scoped exclusively to the compliance-assessment pipeline (always belongs to
an AssessmentSnapshot). This `Finding` is usable by inspections, work
orders, and maintenance tasks directly -- an inspector, technician, or
quality-manager can raise one without running an assessment.

Follows the same dual aircraft_id/asset_id relationship pattern already
established on WorkOrder (app/models/work_order.py) and Component
(app/models/component.py) for aircraft-vs-drone assets, and the same
entity_type/entity_id-traceable shape AssessmentFinding already proves for
"never free-standing prose" findings.

Disposition is a separate sub-model (FindingDisposition), not a text field
on Finding, mirroring how AssessmentGap/AssessmentRecommendation are their
own tables rather than columns bolted onto AssessmentFinding -- a Finding
may go through several disposition attempts (e.g. DEFERRED then later
CORRECTIVE_ACTION) and each carries its own evidence/closure trail, which a
single mutable field would silently overwrite and lose history for.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class FindingSeverity:
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    OBSERVATION = "OBSERVATION"


class FindingStatus:
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"


ALL_FINDING_SEVERITIES = {
    FindingSeverity.CRITICAL,
    FindingSeverity.MAJOR,
    FindingSeverity.MINOR,
    FindingSeverity.OBSERVATION,
}

ALL_FINDING_STATUSES = {
    FindingStatus.OPEN,
    FindingStatus.IN_PROGRESS,
    FindingStatus.CLOSED,
}


class DispositionType:
    CORRECTIVE_ACTION = "CORRECTIVE_ACTION"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    DEFERRED = "DEFERRED"


ALL_DISPOSITION_TYPES = {
    DispositionType.CORRECTIVE_ACTION,
    DispositionType.NO_ACTION_REQUIRED,
    DispositionType.DEFERRED,
}


class Finding(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A general MRO/inspection finding, traceable to a real asset and
    optionally to the component/inspection/work-order it was raised
    against. aircraft_id/asset_id follow the same dual-relationship pattern
    as WorkOrder.aircraft_id/asset_id -- exactly one of them (or neither, if
    the finding is not yet linked to a specific asset) is expected to be
    set, never enforced at the DB layer here since WorkOrder itself does not
    enforce it either (see that model's own comment history).
    """

    __tablename__ = "findings"

    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id"), nullable=True, index=True
    )
    inspection_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspection_requirements.id"), nullable=True, index=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=FindingStatus.OPEN)

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    discovered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # The user currently accountable for resolving this finding -- distinct
    # from discovered_by_user_id (who raised it) and from a disposition's
    # closed_by_user_id (who closed it out).
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    dispositions: Mapped[list["FindingDisposition"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan", order_by="FindingDisposition.created_at"
    )


class FindingDisposition(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """One disposition record on a Finding. A Finding may accumulate more
    than one over its lifetime (e.g. DEFERRED now, CORRECTIVE_ACTION later)
    -- the most recent row is the current disposition; Finding.status is the
    single source of truth for whether the finding itself is open/closed.
    """

    __tablename__ = "finding_dispositions"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.id"), nullable=False, index=True
    )
    disposition_type: Mapped[str] = mapped_column(String(32), nullable=False)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    finding: Mapped[Finding] = relationship(back_populates="dispositions")


__all__ = [
    "Finding",
    "FindingDisposition",
    "FindingSeverity",
    "FindingStatus",
    "DispositionType",
    "ALL_FINDING_SEVERITIES",
    "ALL_FINDING_STATUSES",
    "ALL_DISPOSITION_TYPES",
]
