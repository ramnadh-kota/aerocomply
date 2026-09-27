import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class AssetHistoricalBaseline(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """M5.13: Authoritative Historical Carry-In Baseline for Aircraft & Drones.

    Enables onboarding fleet operational history (cumulative flight hours and
    cycles accrued up to an authoritative effective date) without fabricating
    synthetic individual flight records.

    Accounting Invariant (M5.8 / M5.13):
    Current Asset State = Historical Baseline + SUM(Flights where flown_at >= Baseline.effective_at)
    Flights prior to effective_at remain traceable for audit history but are
    not double-counted.
    """

    __tablename__ = "asset_historical_baselines"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flight_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    flight_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="MANUAL")
    evidence_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


__all__ = ["AssetHistoricalBaseline"]
