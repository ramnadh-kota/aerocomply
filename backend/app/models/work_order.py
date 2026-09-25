import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class WorkOrder(UUIDPKMixin, TenantScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "work_orders"

    # Phase 18.6 (migration 0032): loosened to nullable -- a Drone-based work
    # order has no Aircraft row at all. asset_id (below) is the canonical
    # relationship for those; aircraft_id remains required/populated for
    # every aircraft-based work order exactly as before.
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True
    )
    # Phase 1B compatibility mapping (migration 0031): the canonical
    # generic-asset identity for this work order, backfilled from
    # Aircraft.asset_id wherever it was already set. Nullable for the same
    # reason Aircraft.asset_id itself is nullable -- see that column's
    # docstring. aircraft_id remains the authoritative relationship;
    # service/router logic is unchanged in this phase (see
    # docs/ARCHITECTURE_ASSET_FOUNDATION.md).
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    work_order_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="NORMAL")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
