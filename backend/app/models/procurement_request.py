import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ProcurementRequestStatus:
    """Mirrors frontend/lib/mock/types.ts PartRequestStatus. DRAFT is the only
    state this slice's create() can produce without an explicit submit — every
    other transition goes through procurement_service and is validated there.
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    ORDERED = "ORDERED"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"


class ProcurementRequestPriority:
    ROUTINE = "ROUTINE"
    HIGH = "HIGH"
    AOG = "AOG"


class ProcurementRequest(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "procurement_requests"

    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    part_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id"), nullable=True
    )
    part_number: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProcurementRequestPriority.ROUTINE
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    preferred_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True
    )
    selected_vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ProcurementRequestStatus.DRAFT
    )
    estimated_cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    clarification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
