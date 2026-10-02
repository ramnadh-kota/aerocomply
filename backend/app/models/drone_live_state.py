import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin


class DroneLiveState(TenantScopedMixin, Base):
    """C4: latest known live state per drone (one row per asset). Written only by live_state_service from the
    acquisition pipeline after a PROCESSED event. `payload` is the `kota.drone.live_state.v1` event layer; freshness
    is computed at read time and never stored."""

    __tablename__ = "drone_live_state"
    __table_args__ = (Index("ix_drone_live_state_org_received", "organization_id", "last_received_at"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    last_event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
