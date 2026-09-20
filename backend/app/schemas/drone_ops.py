"""Phase 18.6: request/response schemas for the drone operations vertical
slice (drones/batteries/components/flights/deployment readiness). Mirrors
app/schemas/asset.py and app/schemas/facility.py's style."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DroneCreateRequest(BaseModel):
    registration: str = Field(min_length=1, max_length=16)
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    facility_id: uuid.UUID | None = None


class DroneUpdateRequest(BaseModel):
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)
    facility_id: uuid.UUID | None = None


class DroneResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_type: str
    registration: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    status: str
    facility_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class BatteryCreateRequest(BaseModel):
    serial_number: str = Field(min_length=1, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    capacity_mah: int | None = None
    voltage: int | None = None


class BatteryUpdateRequest(BaseModel):
    health_percent: int | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, max_length=16)
    notes: str | None = None


class BatteryResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID | None
    serial_number: str
    manufacturer: str | None
    model: str | None
    capacity_mah: int | None
    voltage: int | None
    cycle_count: int
    health_percent: int | None
    status: str
    installed_at: datetime | None
    notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ComponentCreateRequest(BaseModel):
    component_type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)


class ComponentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID | None
    component_type: str
    name: str
    serial_number: str | None
    manufacturer: str | None
    model: str | None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class FlightCreateRequest(BaseModel):
    flown_at: datetime
    duration_minutes: int = Field(gt=0)
    cycles: int = Field(default=1, gt=0)
    pilot_user_id: uuid.UUID | None = None
    notes: str | None = None


class FlightResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID
    flown_at: datetime
    duration_minutes: int
    cycles: int
    pilot_user_id: uuid.UUID | None
    notes: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class FlightListResponse(BaseModel):
    items: list[FlightResponse]
    total: int
    limit: int
    offset: int


class UtilizationResponse(BaseModel):
    asset_id: uuid.UUID
    total_flights: int
    total_minutes: int
    total_cycles: int


class FindingBlocker(BaseModel):
    """M21.1: explainable detail for an unresolved-Finding deployment-
    readiness blocker. Mirrors the summary string already appended to
    `blockers` below, but structured so the frontend can link directly to
    the canonical /findings/{id} page instead of parsing free text."""

    finding_id: uuid.UUID
    title: str
    severity: str
    status: str


class DeploymentReadinessResponse(BaseModel):
    asset_id: uuid.UUID
    status: str  # READY | BLOCKED
    blockers: list[str]
    finding_blockers: list[FindingBlocker] = []


# M17.2B: lifecycle history response schemas. Hand-declared projections of
# BatteryInstallation/ComponentInstallation (never `from_attributes` on the
# ORM class blindly re-exported) so a future column doesn't leak here
# without a deliberate schema change -- same convention as
# app/schemas/platform.py's AuditEventResponse.


class BatteryInstallationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    battery_id: uuid.UUID
    asset_id: uuid.UUID
    installed_at: datetime
    removed_at: datetime | None
    installed_by: uuid.UUID | None
    removed_by: uuid.UUID | None

    class Config:
        from_attributes = True


class BatteryInstallationListResponse(BaseModel):
    items: list[BatteryInstallationResponse]
    total: int
    limit: int
    offset: int


class ComponentInstallationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    component_id: uuid.UUID
    asset_id: uuid.UUID
    installed_at: datetime
    removed_at: datetime | None
    installed_by: uuid.UUID | None
    removed_by: uuid.UUID | None

    class Config:
        from_attributes = True


class ComponentInstallationListResponse(BaseModel):
    items: list[ComponentInstallationResponse]
    total: int
    limit: int
    offset: int


class AssetLifecycleEventResponse(BaseModel):
    """One entry in an asset's unified battery+component lifecycle
    timeline. event_type is one of the plain-string constants on
    app.services.installation_service.LifecycleEventType -- deliberately
    not a strict enum on the wire so a future event type doesn't break API
    consumers (same convention as DeploymentReadinessResponse.status)."""

    event_type: str
    occurred_at: datetime
    asset_id: uuid.UUID
    installation_id: uuid.UUID
    battery_id: uuid.UUID | None
    component_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None

    class Config:
        from_attributes = True


class AssetLifecycleHistoryResponse(BaseModel):
    items: list[AssetLifecycleEventResponse]
    total: int
    limit: int
    offset: int
