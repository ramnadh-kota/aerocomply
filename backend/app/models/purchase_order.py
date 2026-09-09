import datetime
import uuid

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class PurchaseOrderStatus:
    """Mirrors frontend/lib/mock/types.ts PurchaseOrderStatus. PARTIALLY_RECEIVED
    and RECEIVED are reachable states in the enum but this slice does not
    implement the transition into them — that's the receiving workflow (M3.8),
    not yet built. Attempting either here raises ConflictError like any other
    unlisted transition.
    """

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CANCELLED = "CANCELLED"


class PurchaseOrder(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PurchaseOrderStatus.DRAFT
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    # All money fields are integer cents, matching VendorPartAvailability.unit_price_cents.
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shipping_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required_by: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    # Only ever set from an actual vendor commitment (see vendor_acknowledged_at) —
    # never fabricated to fill a UI field.
    expected_delivery: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )


class PurchaseOrderLine(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "purchase_order_lines"

    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    procurement_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procurement_requests.id"), nullable=True
    )
    part_number: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    unit_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Quantity actually received against this line — starts at 0, updated only
    # by the receiving workflow (M3.8, not yet built). Present now so that
    # migration doesn't need to touch this table again for a purely additive field.
    received_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
