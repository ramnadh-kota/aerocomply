import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    asset_type: str
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    registration: str | None
    status: str
    acquired_at: datetime | None
    retired_at: datetime | None
    facility_id: uuid.UUID | None = None
    created_at: datetime


class AssetCreateRequest(BaseModel):
    asset_type: str = Field(..., description="AIRCRAFT, DRONE, HELICOPTER, EVTOL, AAM, or OTHER")
    registration: str = Field(..., min_length=1, max_length=16)
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    facility_id: uuid.UUID | None = None
    status: str = Field(default="ACTIVE", max_length=32)


class AssetUpdateRequest(BaseModel):
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    facility_id: uuid.UUID | None = None
    status: str | None = Field(default=None, max_length=32)


# ---------------------------------------------------------------------------
# Components & Configuration
# ---------------------------------------------------------------------------

class AssetComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID | None
    component_type: str
    name: str
    serial_number: str | None
    manufacturer: str | None
    model: str | None
    status: str
    installed_at: datetime | None = None
    created_at: datetime


class AssetInstallComponentRequest(BaseModel):
    component_type: str = Field(..., max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    serial_number: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    notes: str | None = None


class AssetConfigurationSlotResponse(BaseModel):
    slot_name: str
    component_type: str
    is_occupied: bool
    component: AssetComponentResponse | None = None


class AssetConfigurationResponse(BaseModel):
    asset_id: uuid.UUID
    asset_type: str
    airframe_spec: dict[str, Any] = {}
    slots: list[AssetConfigurationSlotResponse] = []
    total_components_installed: int = 0


# ---------------------------------------------------------------------------
# Operations & Utilization
# ---------------------------------------------------------------------------

class AssetFlightCreateRequest(BaseModel):
    flown_at: datetime
    duration_minutes: int = Field(gt=0)
    cycles: int = Field(default=1, gt=0)
    pilot_user_id: uuid.UUID | None = None
    mission_id: uuid.UUID | None = None
    notes: str | None = None


class AssetFlightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID
    mission_id: uuid.UUID | None = None
    flown_at: datetime
    duration_minutes: int
    cycles: int
    pilot_user_id: uuid.UUID | None
    notes: str | None
    created_at: datetime


class UsageMetricItem(BaseModel):
    metric_key: str
    metric_label: str
    value: float
    unit: str
    source: str  # FLIGHT, MISSION, MANUAL, TELEMETRY, SYSTEM
    is_metered: bool = True


class AssetUtilizationResponse(BaseModel):
    asset_id: uuid.UUID
    asset_type: str
    total_flight_hours: float
    total_minutes: int
    total_cycles: int
    total_flights: int
    total_landings: int
    metrics: list[UsageMetricItem] = []


class AssetOperationsResponse(BaseModel):
    asset_id: uuid.UUID
    utilization: AssetUtilizationResponse
    recent_flights: list[AssetFlightResponse] = []
    active_missions: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Maintenance, Inspections, Evidence, Findings, Compliance
# ---------------------------------------------------------------------------

class AssetMaintenanceResponse(BaseModel):
    asset_id: uuid.UUID
    due_items: list[dict[str, Any]] = []
    accomplishments: list[dict[str, Any]] = []
    open_work_orders: list[dict[str, Any]] = []
    has_overdue: bool = False


class AssetInspectionsResponse(BaseModel):
    asset_id: uuid.UUID
    inspections: list[dict[str, Any]] = []
    total: int = 0
    completed: int = 0
    pending: int = 0


class AssetEvidenceResponse(BaseModel):
    asset_id: uuid.UUID
    evidence_items: list[dict[str, Any]] = []
    total: int = 0
    accepted_count: int = 0
    pending_count: int = 0


class AssetFindingsResponse(BaseModel):
    asset_id: uuid.UUID
    findings: list[dict[str, Any]] = []
    total: int = 0
    open_count: int = 0
    closed_count: int = 0


class AssetComplianceResponse(BaseModel):
    asset_id: uuid.UUID
    assessments: list[dict[str, Any]] = []
    overall_status: str  # COMPLIANT | NON_COMPLIANT | REVIEW_REQUIRED | UNKNOWN
    compliant_count: int = 0
    non_compliant_count: int = 0


# ---------------------------------------------------------------------------
# Multi-Dimensional Readiness
# ---------------------------------------------------------------------------

class ReadinessDimension(BaseModel):
    dimension: str  # OPERATIONAL, MAINTENANCE, COMPLIANCE, DEPLOYMENT, RELEASE
    status: str     # READY, AT_RISK, BLOCKED, NOT_APPLICABLE
    summary: str
    blockers: list[str] = []


class AssetReadinessResponse(BaseModel):
    asset_id: uuid.UUID
    overall_status: str  # READY | AT_RISK | BLOCKED
    dimensions: list[ReadinessDimension] = []
    evaluated_at: datetime
    disclaimer: str = (
        "Operational readiness evaluation only. Does not constitute an electronic Release to Service (RTS) signature."
    )


# ---------------------------------------------------------------------------
# Unified Domain History & Context
# ---------------------------------------------------------------------------

class AssetHistoryEventResponse(BaseModel):
    event_id: str
    event_type: str
    occurred_at: datetime
    title: str
    description: str
    actor: str | None = None
    entity_type: str
    entity_id: str
    metadata: dict[str, Any] = {}


class AssetHistoryResponse(BaseModel):
    asset_id: uuid.UUID
    events: list[AssetHistoryEventResponse] = []
    total: int = 0


class AssetDomainContextResponse(BaseModel):
    identity: AssetResponse
    operational_status: str
    lifecycle_status: str
    readiness: AssetReadinessResponse
    configuration: AssetConfigurationResponse
    utilization: AssetUtilizationResponse
    compliance: AssetComplianceResponse
    open_work_orders_count: int
    open_findings_count: int
    overdue_maintenance_count: int
    last_flight_at: datetime | None = None
