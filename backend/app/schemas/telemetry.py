"""M13: Pydantic schemas for Telemetry Ingestion and DJI FlightHub 2 Adapter."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExternalAssetMappingCreate(BaseModel):
    source_system: str = Field(..., max_length=64, description="e.g. DJI_FLIGHTHUB, HUMS_DEVICE")
    external_asset_id: str = Field(..., max_length=128, description="Device SN or serial")
    asset_id: uuid.UUID
    device_model: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class ExternalAssetMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    source_system: str
    external_asset_id: str
    asset_id: uuid.UUID
    device_model: str | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime


class TelemetryReadingItem(BaseModel):
    sensor_code: str = Field(..., max_length=64)
    sensor_type: str = Field(default="TELEMETRY", max_length=64)
    measurement_type: str = Field(..., max_length=64)
    # NaN/Infinity poison baselines, RMS and RUL; Python's JSON parser accepts them, so refuse here.
    value: float = Field(..., allow_inf_nan=False)
    unit: str = Field(..., max_length=32)
    component_id: uuid.UUID | None = None
    data_quality: str = Field(default="VALID", max_length=32)


class TelemetryFlightPayload(BaseModel):
    flight_number: str | None = None
    duration_minutes: int = Field(..., gt=0)
    cycles: int = Field(default=1, ge=1)
    origin: str | None = None
    destination: str | None = None
    flown_at: datetime | None = None
    pilot_user_id: uuid.UUID | None = None
    notes: str | None = None


class TelemetryBatteryPayload(BaseModel):
    serial_number: str = Field(..., max_length=128)
    cycle_count: int | None = Field(default=None, ge=0)
    voltage_v: float | None = Field(default=None, allow_inf_nan=False)
    internal_resistance_mohm: float | None = Field(default=None, allow_inf_nan=False)
    temperature_c: float | None = Field(default=None, allow_inf_nan=False)
    health_percent: int | None = Field(default=None, ge=0, le=100)
    cell_voltages: list[float] | None = None


class NormalizedTelemetryEvent(BaseModel):
    source_system: str = Field(..., max_length=64)
    source_event_id: str = Field(..., max_length=128)
    source_asset_id: str = Field(..., max_length=128)
    event_type: str = Field(
        ...,
        max_length=64,
        description="FLIGHT_COMPLETED | TELEMETRY_PING | BATTERY_STATE | SENSOR_BURST",
    )
    event_timestamp: datetime
    flight: TelemetryFlightPayload | None = None
    battery: TelemetryBatteryPayload | None = None
    readings: list[TelemetryReadingItem] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class TelemetryIngestRequest(BaseModel):
    events: list[NormalizedTelemetryEvent] = Field(..., min_length=1)


class TelemetryEventResult(BaseModel):
    source_event_id: str
    status: str  # PROCESSED | DUPLICATE | REJECTED | QUARANTINED | FAILED
    asset_id: uuid.UUID | None = None
    flight_id: uuid.UUID | None = None
    readings_count: int = 0
    message: str | None = None


class TelemetryIngestResponse(BaseModel):
    total_received: int
    processed_count: int
    duplicate_count: int
    rejected_count: int
    results: list[TelemetryEventResult]


class DJIFlightHubWebhookPayload(BaseModel):
    """DJI FlightHub 2 Webhook event schema wrapper.

    Contract:
    - bid: Business ID / Event ID
    - tid: Trace ID
    - event: Event Name (e.g. 'flight_record.created', 'device.osd.telemetry', 'battery.status')
    - timestamp: Millisecond Epoch or ISO timestamp
    - data: Event payload dictionary containing device_sn, flight details, battery metrics.
    """

    bid: str = Field(..., description="Unique event business ID")
    tid: str | None = None
    event: str = Field(..., description="DJI event type")
    timestamp: int | str = Field(..., description="Timestamp of event generation")
    data: dict[str, Any] = Field(..., description="DJI FlightHub payload body")


class TelemetryFreshnessPolicyBase(BaseModel):
    asset_id: uuid.UUID | None = None
    source_system: str | None = None
    warning_threshold_days: int = Field(default=7, ge=1, le=365)
    critical_threshold_days: int = Field(default=14, ge=1, le=730)
    is_active: bool = True
    description: str | None = Field(default=None, max_length=255)


class TelemetryFreshnessPolicyCreate(TelemetryFreshnessPolicyBase):
    pass


class TelemetryFreshnessPolicyUpdate(BaseModel):
    warning_threshold_days: int | None = Field(default=None, ge=1, le=365)
    critical_threshold_days: int | None = Field(default=None, ge=1, le=730)
    is_active: bool | None = None
    description: str | None = None


class TelemetryFreshnessPolicyResponse(TelemetryFreshnessPolicyBase):
    id: uuid.UUID
    organization_id: uuid.UUID
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

