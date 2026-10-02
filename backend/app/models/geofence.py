import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class Geofence(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """C5: tenant-scoped operational zone. ADVISORY operational data -- never legal airspace authorisation.

    `kind`: RESTRICTED (entering is a violation), CAUTION (entering is a lower-severity violation) or OPERATING_AREA
    (LEAVING is the violation). Geometry follows app/services/geo.py (WGS84, rings are [lon, lat]). Every change bumps
    `version` and writes a `geofence_versions` snapshot; zones are deactivated, never deleted."""

    __tablename__ = "geofences"
    __table_args__ = (Index("ix_geofences_org_active", "organization_id", "is_active"),)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    geometry: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    altitude_reference: Mapped[str] = mapped_column(String(16), nullable=False, default="HOME_RELATIVE")
    alt_min_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    alt_max_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="HIGH")
    proximity_buffer_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    boundary_tolerance_m: Mapped[float] = mapped_column(Float, nullable=False, default=5.0)
    confirm_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    asset_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)  # None = every drone of the tenant
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GeofenceVersion(UUIDPKMixin, TenantScopedMixin, Base):
    """Immutable configuration history: one full snapshot per geofence version."""

    __tablename__ = "geofence_versions"
    __table_args__ = (UniqueConstraint("geofence_id", "version", name="uq_geofence_version"),)

    geofence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geofences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LiveRuleState(UUIDPKMixin, TenantScopedMixin, Base):
    """Per (asset, rule) evaluation memory for the live alert evaluator: the confirmed state, the debounce candidate,
    the current episode and the M7 signal that episode raised. Derived data (rebuildable); the alert itself is owned by
    `proactive_signal_records` (M7)."""

    __tablename__ = "live_rule_state"
    __table_args__ = (UniqueConstraint("organization_id", "asset_id", "rule_key", name="uq_live_rule_state"),)

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_key: Mapped[str] = mapped_column(String(160), nullable=False)  # geofence:<id> | low_battery | telemetry_loss
    geofence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("geofences.id", ondelete="CASCADE"), nullable=True, index=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    candidate_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    condition: Mapped[str | None] = mapped_column(String(24), nullable=True)  # BREACH | PROXIMITY | WARNING | CRITICAL
    episode: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proactive_signal_records.id", ondelete="SET NULL"), nullable=True
    )
    rule_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_signed_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


__all__ = ["Geofence", "GeofenceVersion", "LiveRuleState"]
