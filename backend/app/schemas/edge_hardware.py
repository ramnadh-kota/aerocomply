"""M14/M16: Edge Hardware, Productization & Telemetry Envelope Schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class EdgeDeviceLifecycleStatus:
    PROVISIONING = "PROVISIONING"
    REGISTERED = "REGISTERED"
    CONFIGURED = "CONFIGURED"
    CONNECTED = "CONNECTED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    RECOVERY = "RECOVERY"
    DECOMMISSIONING = "DECOMMISSIONING"
    RETIRED = "RETIRED"
    REVOKED = "REVOKED"


class EdgeDeviceCreate(BaseModel):
    device_id: str = Field(..., max_length=128, description="Unique hardware/device serial or MAC")
    gateway_id: str | None = Field(None, max_length=128, description="Parent gateway ID if connected via mesh/hub")
    asset_id: uuid.UUID | None = Field(None, description="Bound KOTA Asset ID")
    device_type: str = Field("SENSOR_NODE", max_length=64, description="SENSOR_NODE | EDGE_GATEWAY | OBD_LOGGER")
    firmware_version: str | None = Field(None, max_length=64)
    metadata_json: dict[str, Any] | None = None


class EdgeDeviceResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    device_id: str
    gateway_id: str | None
    asset_id: uuid.UUID | None
    device_type: str
    firmware_version: str | None
    status: str
    last_heartbeat_at: datetime | None
    metadata_json: dict[str, Any] | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class EdgeSensorItem(BaseModel):
    sensor_code: str = Field(..., description="e.g. MOT_1_VIB, ENG_1_TEMP, HYD_PRESS, BUS_ELEC")
    sensor_type: str = Field("VIBRATION", description="VIBRATION | TEMPERATURE | PRESSURE | ELECTRICAL | IMU")
    model: str | None = Field(None, description="Physical sensor part number / model")
    serial_number: str | None = Field(None, description="Sensor hardware serial number")
    channel: str | None = Field("CH1", description="Hardware bus / port / ADC channel")
    unit: str = Field("g", description="e.g. g, mm/s, degC, bar, V, A")
    status: str = Field("ACTIVE", description="ACTIVE | CALIBRATION_DUE | FAULT | INACTIVE")
    calibration_metadata: dict[str, Any] | None = None


class EdgeDeviceProvisionRequest(BaseModel):
    device_id: str = Field(..., max_length=128, description="Unique hardware node identifier")
    device_type: str = Field("EDGE_GATEWAY", max_length=64)
    gateway_id: str | None = None
    asset_id: uuid.UUID | None = None
    firmware_version: str | None = Field("2.6.0-m16")
    sensors: list[EdgeSensorItem] = Field(default_factory=list)
    initial_config: dict[str, Any] | None = None
    auth_secret: str | None = Field(None, description="Optional pre-shared hardware provision token")
    hardware_metadata: dict[str, Any] | None = None


class EdgeDeviceProvisionResponse(BaseModel):
    device: EdgeDeviceResponse
    provisioning_token: str
    config_version: int
    lifecycle_stage: str


class EdgeDeviceConfigUpdate(BaseModel):
    settings: dict[str, Any] = Field(
        ...,
        description="Configuration parameters (sampling_hz, telemetry_rate_sec, buffer_limit, channels)",
    )
    change_summary: str | None = Field("Operational parameter update")
    apply_immediately: bool = True


class EdgeDeviceConfigResponse(BaseModel):
    device_id: str
    active_version: int
    applied_at: datetime | None
    settings: dict[str, Any]
    history: list[dict[str, Any]] = Field(default_factory=list)


class EdgeDeviceHeartbeatRequest(BaseModel):
    device_id: str
    timestamp: datetime
    firmware_version: str | None = None
    software_version: str | None = None
    uptime_seconds: int | None = None
    connectivity_state: str | None = Field("ONLINE", description="ONLINE | DEGRADED | CELLULAR_BACKUP")
    sensor_states: dict[str, str] | None = Field(default_factory=dict, description="sensor_code -> status")
    queue_depth: int | None = 0
    config_version: int | None = 1
    observability: dict[str, Any] | None = None


class EdgeDeviceHeartbeatResponse(BaseModel):
    status: str
    server_time: datetime
    pending_commands_count: int
    latest_config_version: int | None
    requires_config_sync: bool


class EdgeDeviceCommandRequest(BaseModel):
    command_type: Literal[
        "REQUEST_HEARTBEAT",
        "REQUEST_CONFIG",
        "APPLY_CONFIG",
        "RESTART_ACQUISITION",
        "REQUEST_DIAGNOSTICS",
        "SET_SAMPLING_RATE",
    ]
    parameters: dict[str, Any] | None = None


class EdgeDeviceCommandResponse(BaseModel):
    command_id: str
    device_id: str
    command_type: str
    status: str
    issued_at: datetime
    executed_at: datetime | None = None
    result: dict[str, Any] | None = None


class EdgeDeviceCommandResultSubmit(BaseModel):
    command_id: str
    status: Literal["SUCCESS", "FAILED"]
    result: dict[str, Any] | None = None
    error_message: str | None = None


class EdgeDeviceRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=3, description="Justification for device revocation")


class EdgeDeviceRevokeResponse(BaseModel):
    device_id: str
    status: str
    revoked_at: datetime
    reason: str


class EdgeSensorMeasurement(BaseModel):
    sensor_code: str = Field(..., description="e.g. MOT_1_VIB, ENG_1_EGT, BAT_VOLT")
    sensor_type: str = Field("VIBRATION", description="VIBRATION | TEMPERATURE | PRESSURE | ELECTRICAL | IMU")
    timestamp: datetime
    unit: str = Field("g", description="e.g. g, degC, bar, V, A")
    raw_values: dict[str, float] = Field(default_factory=dict, description="e.g. {'rms_g': 0.42, 'peak_g': 1.2}")
    quality: Literal["VALID", "SUSPECT", "OUT_OF_RANGE", "STALE", "INVALID"] = "VALID"


class DeviceTelemetryEnvelope(BaseModel):
    """Canonical edge hardware telemetry envelope (M14/M16)."""
    device_id: str = Field(..., description="Reporting hardware node identifier")
    gateway_id: str | None = Field(None, description="Intermediary edge gateway ID")
    firmware_version: str | None = Field("1.0.0")
    source_asset_id: str | None = Field(None, description="Asset serial or registration number")
    sequence_number: int = Field(1, ge=1, description="Monotonically increasing sequence number")
    envelope_timestamp: datetime
    measurements: list[EdgeSensorMeasurement] = Field(default_factory=list)
    signature: str | None = Field(None, description="HMAC or ECDSA hardware signature for tamper detection")
