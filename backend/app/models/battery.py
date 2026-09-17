import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class BatteryStatus:
    GOOD = "GOOD"
    MONITOR = "MONITOR"
    SERVICE_DUE = "SERVICE_DUE"
    CRITICAL = "CRITICAL"
    RETIRED = "RETIRED"


class Battery(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Phase 18.6: a serialized, health-tracked battery -- NOT a Part (see
    alembic/versions/0032_drone_operations.py's docstring for why Part's
    quantity-counting shape doesn't fit). asset_id is the ONE relationship
    identifying which asset currently carries this battery; nullable
    because a battery can exist in inventory before being installed. No
    field on Asset points back -- this column is the single source of
    truth for "which battery is on this drone right now.\""""

    __tablename__ = "batteries"

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capacity_mah: Mapped[int | None] = mapped_column(Integer, nullable=True)
    voltage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Incremented by flight_service on each flight this battery is attached
    # for -- never manually overwritten by a user-editable field, matching
    # the milestone's utilization-integrity requirement.
    cycle_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=BatteryStatus.GOOD)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
