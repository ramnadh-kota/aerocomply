from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class AssetType(StrEnum):
    """Discriminator for the generic Asset foundation (Phase 1A).

    Only AIRCRAFT is backed by a detail table today (AircraftDetail) and only
    AIRCRAFT assets exist in the database as of this phase -- DRONE is added
    here only so future phases can extend AssetType without another schema
    change to this column. See docs/ARCHITECTURE_ASSET_FOUNDATION.md.
    """

    AIRCRAFT = "AIRCRAFT"
    DRONE = "DRONE"


class Asset(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Generic aerospace asset identity, shared across asset types.

    Asset holds the fields every asset type has in common (tenant ownership,
    identity, status, lifecycle). Type-specific fields live on a 1:1 detail
    table keyed by asset_id (e.g. AircraftDetail) -- see
    docs/ARCHITECTURE_ASSET_FOUNDATION.md for why this split was chosen over
    a single wide table or single-table inheritance.

    manufacturer/model/serial_number are nullable: the existing Aircraft
    table has no reliable source for these fields, and Phase 1A's backfill
    must not invent values (see the migration for 0027).
    """

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "registration", name="uq_assets_organization_id_registration"
        ),
    )

    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registration: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
