import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Aircraft(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "aircraft"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "registration", name="uq_aircraft_organization_id_registration"
        ),
        UniqueConstraint("asset_id", name="uq_aircraft_asset_id"),
    )

    registration: Mapped[str] = mapped_column(String(16), nullable=False)
    msn: Mapped[str] = mapped_column(String(64), nullable=False)
    aircraft_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    # Phase 1A compatibility mapping: the deterministic, DB-backed link to
    # this Aircraft's generic Asset row, backfilled by migration 0027 for
    # every pre-existing row. Nullable because this column, table, and the
    # Asset/AircraftDetail split are purely additive -- no existing FK
    # (work_orders.aircraft_id, compliance.aircraft_id, etc.) changes in this
    # phase, so Aircraft remains fully usable even where asset_id is unset.
    # See docs/ARCHITECTURE_ASSET_FOUNDATION.md.
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=True
    )
