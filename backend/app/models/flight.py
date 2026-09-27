import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Flight(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """M5.1 / Phase 18.6: The authoritative operational record and utilization source of truth
    for all aerospace assets (Aircraft and Drones).

    Deliberately asset-native (NOT NULL asset_id). Operational utilization is derived
    from immutable Flight records and authoritative AssetHistoricalBaselines.
    """

    __tablename__ = "flights"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    flight_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(64), nullable=True)
    departure_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrival_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mission_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED", index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    source_row_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    pilot_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

