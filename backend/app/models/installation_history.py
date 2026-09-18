import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class BatteryInstallation(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Phase 18.6/M17.2A: one row per install-to-removal span of a
    Battery on an Asset. Battery.asset_id (see that model's docstring)
    remains the single source of truth for "where is it right now" --
    this table is purely additive history, never read to resolve current
    state. A partial unique index (removed_at IS NULL) enforces at most
    one open/active installation per battery at the database level -- see
    alembic/versions/0033_installation_history.py."""

    __tablename__ = "battery_installations"
    __table_args__ = (
        Index(
            "uq_battery_installations_battery_id_open",
            "battery_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    battery_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("batteries.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    installed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    removed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class ComponentInstallation(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Same purpose and shape as BatteryInstallation, for Component. See
    that model's docstring."""

    __tablename__ = "component_installations"
    __table_args__ = (
        Index(
            "uq_component_installations_component_id_open",
            "component_id",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
        ),
    )

    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    installed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    removed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
