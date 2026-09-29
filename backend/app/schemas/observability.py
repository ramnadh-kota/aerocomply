"""Schemas for M13 Phase 5 Observability & Hypercare."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OperationalIncidentCreate(BaseModel):
    severity: str = Field("P2", description="P0, P1, P2, P3")
    service_name: str = Field(..., description="AUTH_SSO, TELEMETRY, HUMS, INTELLIGENCE, OPERATIONS, INFRASTRUCTURE")
    title: str = Field(..., max_length=255)
    description: str
    asset_id: uuid.UUID | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class OperationalIncidentUpdate(BaseModel):
    severity: str | None = None
    status: str | None = None
    title: str | None = None
    description: str | None = None
    details: dict[str, Any] | None = None


class OperationalIncidentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    severity: str
    service_name: str
    title: str
    description: str
    status: str
    asset_id: uuid.UUID | None
    first_detected_at: datetime
    resolved_at: datetime | None
    acknowledged_by_user_id: uuid.UUID | None
    details: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class HypercareMetricCount(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    pending: int = 0


class TelemetrySummary(BaseModel):
    total_events: int = 0
    processed_count: int = 0
    duplicate_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
    active_assets_reporting: int = 0


class HUMSSummary(BaseModel):
    sensor_count: int = 0
    active_sensors: int = 0
    readings_count: int = 0
    exceedance_count: int = 0
    diagnostic_candidates_count: int = 0


class IntelligenceSummary(BaseModel):
    active_signals_count: int = 0
    critical_signals_count: int = 0
    open_findings_count: int = 0


class IncidentsSummary(BaseModel):
    open_p0: int = 0
    open_p1: int = 0
    open_p2: int = 0
    open_p3: int = 0
    total_open: int = 0


class HypercareSummaryResponse(BaseModel):
    timestamp: datetime
    organization_id: uuid.UUID
    platform_status: str  # OPERATIONAL | DEGRADED | CRITICAL
    telemetry: TelemetrySummary
    hums: HUMSSummary
    intelligence: IntelligenceSummary
    incidents: IncidentsSummary
    auth_sso_configured: bool = False
