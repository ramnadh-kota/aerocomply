"""B1: DataSource — Persistent, tenant-scoped connector configuration model.

Architecture Invariants:
- Each DataSource record describes one configured acquisition connector for a tenant.
- connector_type is the canonical protocol tag (MAVLINK | MQTT | DJI_FLIGHTHUB |
  CSV_BATCH | JSON_BATCH | OEM_API | GENERIC_WEBHOOK).
- connection_config stores protocol-specific parameters (broker URL, topic, port, etc.).
  Secret credentials (passwords, API keys) are NEVER stored here; they are referenced by
  secret_reference and resolved at runtime via the platform secrets layer.
- Tenant context is established before any acquisition begins (organization_id is mandatory
  and validated against the authenticated session).
- Status lifecycle: DRAFT → ACTIVE → PAUSED → DECOMMISSIONED.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class DataSourceConnectorType:
    """Canonical connector type identifiers."""

    MAVLINK = "MAVLINK"
    MQTT = "MQTT"
    DJI_FLIGHTHUB = "DJI_FLIGHTHUB"
    CSV_BATCH = "CSV_BATCH"
    JSON_BATCH = "JSON_BATCH"
    OEM_API = "OEM_API"
    GENERIC_WEBHOOK = "GENERIC_WEBHOOK"

    ALL: frozenset[str] = frozenset(
        {MAVLINK, MQTT, DJI_FLIGHTHUB, CSV_BATCH, JSON_BATCH, OEM_API, GENERIC_WEBHOOK}
    )


class DataSourceStatus:
    """DataSource operational lifecycle states."""

    DRAFT = "DRAFT"                     # Configured but not yet enabled
    ACTIVE = "ACTIVE"                   # Live acquisition enabled
    PAUSED = "PAUSED"                   # Temporarily suspended (no data ingestion)
    DECOMMISSIONED = "DECOMMISSIONED"   # Permanently retired


class DataSource(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Tenant-scoped, persistent configuration for a single data acquisition connector.

    One DataSource = one physical or logical connection to a data origin.
    e.g.: A single MQTT broker subscription, a MAVLink UDP endpoint, a DJI FlightHub
    webhook receiver, a recurring CSV drop-zone, or an OEM REST API endpoint.
    """

    __tablename__ = "data_sources"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_data_sources_org_name",
        ),
        Index("ix_data_sources_org_type", "organization_id", "connector_type"),
        Index("ix_data_sources_org_status", "organization_id", "status"),
    )

    # Human-readable name within the tenant (unique per org)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Short description of what this source represents
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Canonical connector type
    connector_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Protocol-specific connection parameters (no secrets)
    # e.g. {"host": "broker.example.com", "port": 1883, "topic": "kota/telemetry/#"}
    connection_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # Reference to the platform secrets store key for credentials (never inline)
    # e.g. "datasource/org-uuid/source-uuid/mqtt_password"
    secret_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Operational lifecycle status
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DataSourceStatus.DRAFT
    )

    # Acquisition health observability
    last_acquisition_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_events_ingested: Mapped[int] = mapped_column(nullable=False, default=0)
    total_events_rejected: Mapped[int] = mapped_column(nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(nullable=False, default=0)

    # Optional: bind this connector to a specific asset (for single-asset sources)
    default_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Additional metadata (tags, owner contact, integration version, etc.)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
