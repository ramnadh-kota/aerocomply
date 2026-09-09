import datetime
import uuid

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class DeferredItemCategory:
    """MEL category — governs the maximum allowable deferral period under a
    real MEL/CDL. UNKNOWN is a legitimate, honest value: most records will
    not have a category on file (mirrors frontend/lib/mock/types.ts).
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    UNKNOWN = "UNKNOWN"


class DeferredItemBasis:
    MEL = "MEL"
    CDL = "CDL"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class DeferredItemApprovalStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    NOT_REQUIRED = "NOT_REQUIRED"


class DeferredItemStatus:
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class DeferredItem(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "deferred_items"

    aircraft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False, index=True
    )
    work_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True
    )
    mel_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DeferredItemCategory.UNKNOWN
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    opened_at: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    # null = UNKNOWN, never a guessed deadline — same rule the frontend type
    # documents (frontend/lib/mock/types.ts DeferredItem.dueAt).
    due_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DeferredItemStatus.OPEN
    )
    deferral_basis: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DeferredItemBasis.UNKNOWN
    )
    # Free-text operational limitation/placard text — NEVER auto-generated.
    # Null means "insufficient source data", not "no limitation exists".
    operational_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plain text, one action per line — same simplification precedent as
    # Vendor.certifications (a small display-only list, not queried
    # individually), rather than introducing a child table for this slice.
    required_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DeferredItemApprovalStatus.NOT_REQUIRED
    )
    closed_at: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    closure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
