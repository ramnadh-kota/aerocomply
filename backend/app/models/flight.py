import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Flight(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Phase 18.6: the utilization source of truth for a drone asset.
    Deliberately asset-native (NOT NULL asset_id, no aircraft_id
    compatibility concept) -- unlike the Phase 1B MRO tables, Flight is a
    brand-new domain with no pre-existing aircraft-centric history to be
    compatible with. Asset.status/utilization is never manually
    overwritten -- flight_service.get_utilization sums these rows, the
    same "records are the source of truth, not a mutable counter" pattern
    as the rest of this codebase's audit-first conventions.
    """

    __tablename__ = "flights"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mission_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    flown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    pilot_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
