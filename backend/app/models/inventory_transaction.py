import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class InventoryTransactionType:
    """Movements this slice actually implements against Part.quantity_on_hand /
    quantity_reserved / quantity_quarantined. RECEIVE increases on_hand;
    RESERVE/RELEASE move reserved; CONSUME reduces both on_hand and reserved
    (issued against a reservation); ADJUST is a manual correction (can be
    positive or negative) for cycle counts; QUARANTINE/RELEASE_QUARANTINE
    move stock into/out of quantity_quarantined (excluded from
    available_quantity while quarantined — see app/models/part.py).
    """

    RECEIVE = "RECEIVE"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    CONSUME = "CONSUME"
    ADJUST = "ADJUST"
    QUARANTINE = "QUARANTINE"
    RELEASE_QUARANTINE = "RELEASE_QUARANTINE"


class InventoryTransaction(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "inventory_transactions"

    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id"), nullable=False, index=True
    )
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Signed delta applied to Part.quantity_on_hand for this transaction (0 if the
    # transaction only moves reserved, e.g. RESERVE/RELEASE).
    on_hand_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Signed delta applied to Part.quantity_reserved for this transaction.
    reserved_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Signed delta applied to Part.quantity_quarantined for this transaction.
    quarantined_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Optional traceability back to the work order / part requirement that drove
    # this movement — nullable because a manual ADJUST may have no such origin.
    reference_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
