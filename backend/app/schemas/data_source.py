"""B1: Pydantic schemas for DataSource acquisition connector management API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.data_source import DataSourceConnectorType, DataSourceStatus


class DataSourceCreate(BaseModel):
    """Request schema for registering a new data acquisition connector."""

    name: str = Field(..., min_length=1, max_length=128, description="Unique name within organization")
    description: str | None = Field(default=None, max_length=512)
    connector_type: str = Field(
        ...,
        description="Protocol type: MAVLINK | MQTT | DJI_FLIGHTHUB | CSV_BATCH | JSON_BATCH | OEM_API | GENERIC_WEBHOOK",
    )
    connection_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Protocol connection parameters (no secrets — use secret_reference for credentials)",
    )
    secret_reference: str | None = Field(
        default=None,
        max_length=255,
        description="Platform secrets store key for credentials (e.g. 'datasource/org-id/src-id/password')",
    )
    default_asset_id: uuid.UUID | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("connector_type")
    @classmethod
    def validate_connector_type(cls, v: str) -> str:
        if v not in DataSourceConnectorType.ALL:
            raise ValueError(
                f"connector_type must be one of: {sorted(DataSourceConnectorType.ALL)}"
            )
        return v


class DataSourceUpdate(BaseModel):
    """Request schema for updating an existing data acquisition connector."""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    connection_config: dict[str, Any] | None = None
    secret_reference: str | None = None
    status: str | None = None
    default_asset_id: uuid.UUID | None = None
    metadata_json: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {
            DataSourceStatus.DRAFT,
            DataSourceStatus.ACTIVE,
            DataSourceStatus.PAUSED,
            DataSourceStatus.DECOMMISSIONED,
        }
        if v not in allowed:
            raise ValueError(f"status must be one of: {sorted(allowed)}")
        return v


class DataSourceResponse(BaseModel):
    """Response schema for a data acquisition connector."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    connector_type: str
    connection_config: dict[str, Any]
    secret_reference: str | None
    status: str
    last_acquisition_at: datetime | None
    total_events_ingested: int
    total_events_rejected: int
    consecutive_failures: int
    default_asset_id: uuid.UUID | None
    metadata_json: dict[str, Any] | None
    created_at: datetime


class DataSourceListResponse(BaseModel):
    """Paginated list response for data sources."""

    total: int
    items: list[DataSourceResponse]


class DataSourceAcquisitionStats(BaseModel):
    """Lightweight health/statistics view of a data source."""

    id: uuid.UUID
    name: str
    connector_type: str
    status: str
    last_acquisition_at: datetime | None
    total_events_ingested: int
    total_events_rejected: int
    consecutive_failures: int
    health: str  # HEALTHY | DEGRADED | FAILED | INACTIVE
