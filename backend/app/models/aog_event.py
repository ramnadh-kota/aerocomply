import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class AogEventStatus:
    DECLARED = "DECLARED"
    IN_RECOVERY = "IN_RECOVERY"
    RECOVERED = "RECOVERED"
    CANCELLED = "CANCELLED"


class AogSeverity:
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"


class AogBlockerType:
    MATERIAL = "MATERIAL"
    TECHNICIAN = "TECHNICIAN"
    INSPECTION = "INSPECTION"
    EVIDENCE = "EVIDENCE"
    REGULATORY = "REGULATORY"
    DEFERRED = "DEFERRED"
    SAFETY = "SAFETY"
    OTHER = "OTHER"


class AogEvent(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """A declared AOG (Aircraft On Ground) event. Deliberately does NOT attempt
    to auto-derive blockers by re-deriving cross-domain analysis the way the
    frontend's getAogRecoveryAnalysis does (it draws on Deferred/MEL and
    Compliance data that has no backend domain yet as of M3.9) — blockers here
    are explicit, human-recorded AogBlocker rows tied to whatever real backend
    record (work order, part requirement, etc.) is actually driving the delay.
    A fabricated auto-derived blocker list would violate the no-fake-data rule
    worse than an honestly incomplete one.
    """

    __tablename__ = "aog_events"

    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AogEventStatus.DECLARED
    )
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AogSeverity.CRITICAL
    )
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    declared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    recovery_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    blockers: Mapped[list["AogBlocker"]] = relationship(
        back_populates="aog_event", cascade="all, delete-orphan"
    )


class AogBlocker(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "aog_blockers"

    aog_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aog_events.id"), nullable=False, index=True
    )
    blocker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Free-text pointer to the real record driving this blocker (e.g. a part
    # requirement id, a PO number) — not a hard FK since the source record
    # type varies (Part, ProcurementRequest, InspectionRequirement, ...) and
    # this codebase has no polymorphic-reference pattern established yet.
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    aog_event: Mapped[AogEvent] = relationship(back_populates="blockers")
