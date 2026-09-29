"""M13: Telemetry domain models for source provenance, external asset mapping, and deterministic idempotency.

Architecture:
- ExternalAssetMapping: Maps tenant-scoped external provider asset IDs (e.g. DJI FlightHub 2 aircraft SN)
  to internal KOTA Asset IDs.
- TelemetryEventLog: Ingestion log storing provenance, SHA-256 payload hash, and processing status
  for strict deterministic idempotency and forensic auditing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ExternalAssetMapping(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Maps an external provider's device/serial/asset identifier to a KOTA Asset within a tenant."""

    __tablename__ = "external_asset_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_system",
            "external_asset_id",
            name="uq_ext_asset_map_org_source_extid",
        ),
        Index("ix_ext_asset_map_org_source", "organization_id", "source_system"),
        Index("ix_ext_asset_map_org_asset", "organization_id", "asset_id"),
    )

    source_system: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # DJI_FLIGHTHUB | HUMS_DEVICE | GENERIC_TELEMETRY
    external_asset_id: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # e.g. "FC30-0981", "DRONE-SN-123"
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TelemetryProcessingStatus:
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    PROCESSED = "PROCESSED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


class TelemetryEventLog(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Audit & idempotency log for all ingested telemetry events."""

    __tablename__ = "telemetry_event_logs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_system",
            "source_event_id",
            name="uq_telemetry_event_org_source_eventid",
        ),
        Index(
            "ix_telemetry_event_org_status",
            "organization_id",
            "processing_status",
        ),
        Index("ix_telemetry_event_org_ts", "organization_id", "event_timestamp"),
    )

    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_asset_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    flight_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flights.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # FLIGHT_COMPLETED | TELEMETRY_PING | BATTERY_STATE | SENSOR_BURST
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of raw body
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TelemetryProcessingStatus.RECEIVED
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    readings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class TelemetryFreshnessPolicy(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Configurable freshness thresholds (warning & critical days) by tenant, operational asset, or telemetry source."""

    __tablename__ = "telemetry_freshness_policies"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "asset_id",
            "source_system",
            name="uq_freshness_policy_org_asset_source",
        ),
        Index("ix_freshness_policy_org_asset", "organization_id", "asset_id"),
    )

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warning_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    critical_threshold_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class EdgeDevice(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Hardware device / edge gateway registered to an organization and optionally bound to an asset."""

    __tablename__ = "edge_devices"
    __table_args__ = (
        UniqueConstraint("organization_id", "device_id", name="uq_edge_devices_org_device_id"),
        Index("ix_edge_devices_org_status", "organization_id", "status"),
        Index("ix_edge_devices_asset", "asset_id"),
    )

    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    gateway_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    device_type: Mapped[str] = mapped_column(String(64), nullable=False, default="SENSOR_NODE")
    firmware_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

