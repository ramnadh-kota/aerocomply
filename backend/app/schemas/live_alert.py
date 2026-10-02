"""C5: operational alert contract served by /live/alerts and pushed as SSE `alert` events.

An alert IS an M7 `ProactiveSignalRecord` (single owner of fleet attention and its lifecycle); this is a stable,
live-oriented projection of it. Geofence output is advisory operational information, never airspace authorisation."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "kota.drone.live_alert.v1"
LIVE_ALERT_TYPES = ("GEOFENCE_BREACH", "GEOFENCE_PROXIMITY", "LIVE_LOW_BATTERY", "LIVE_TELEMETRY_LOSS")
ACTIVE_STATUSES = ("OPEN", "ACKNOWLEDGED", "IN_REVIEW")
AlertChange = Literal[
    "raised", "updated", "cleared", "auto_resolved", "acknowledged", "in_review", "resolved", "dismissed", "reopened"
]


class LiveAlertV1(BaseModel):
    schema_: Literal["kota.drone.live_alert.v1"] = Field(SCHEMA_VERSION, alias="schema")
    id: uuid.UUID
    alert_type: str
    severity: str
    status: str
    condition_active: bool = Field(
        ..., description="False once the triggering condition has cleared; the alert may still await operator action"
    )
    asset_id: uuid.UUID | None
    asset_registration: str | None = None
    geofence_id: uuid.UUID | None = None
    title: str
    headline: str
    explanation: list[str]
    detected_at: datetime
    cleared_at: datetime | None = None
    cleared_reason: str | None = None
    rule: dict[str, Any] = Field(default_factory=dict, description="rule name, rule_version (geofence version), episode")
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict, description="state_version, event time, position quality")
    acknowledged_by_user_id: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    resolved_by_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None
    dismissed_at: datetime | None = None
    dismissal_reason: str | None = None
    reopen_count: int = 0
    advisory: str = "Operational information only; not authoritative airspace authorisation or a flight command."

    model_config = {"populate_by_name": True}


class LiveAlertList(BaseModel):
    alerts: list[LiveAlertV1]
    total: int


class AlertActionRequest(BaseModel):
    notes: str | None = Field(None, max_length=2000)
