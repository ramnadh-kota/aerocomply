"""M7: Proactive Aerospace Intelligence, Risk & Decision Automation Schemas.

Defines the structured contracts for proactive intelligence signals, evidence provenance,
action items, lifecycle mutations, and command-center intelligence summaries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SignalType = Literal[
    "MAINTENANCE_THRESHOLD",
    "INSPECTION_THRESHOLD",
    "COMPONENT_LIFE_LIMIT",
    "RECURRING_FINDING",
    "UTILIZATION_TREND",
    "COMPLIANCE_RISK",
    "EVIDENCE_GAP",
    "READINESS_DEGRADATION",
    "FLEET_PATTERN",
    # H1: HUMS vibration threshold exceedance — extends the M7 taxonomy
    # rather than introducing a parallel signal system (see hums_service.py).
    "HUMS_VIBRATION_EXCEEDANCE",
    # H3: HUMS baseline-driven health deterioration (DEGRADED/WARNING/
    # CRITICAL only — see app/services/hums/health_service.py::sync_health_signal).
    "HUMS_HEALTH_DEGRADATION",
    # H4: rule-based diagnostic candidate generated — never a confirmed
    # fault (see app/services/hums/diagnostic_service.py::sync_diagnostic_signal).
    "HUMS_DIAGNOSTIC_CANDIDATE",
    # H5: RUL entered its configured warning window, or the prognostic
    # model/estimate became LOW_CONFIDENCE/STALE (see
    # app/services/hums/prognostic_service.py::_sync_rul_signal).
    "HUMS_RUL_WARNING",
    "HUMS_EXCEEDANCE",
    # M13: Telemetry freshness & data quality early-warning signals
    "TELEMETRY_FRESHNESS",
    # C5: live operational alerts raised by app/services/live_alert_service.py. They reuse this M7 record/lifecycle;
    # LIVE_TELEMETRY_LOSS is seconds-scale (armed drone went silent) and distinct from the days-scale TELEMETRY_FRESHNESS.
    "GEOFENCE_BREACH",
    "GEOFENCE_PROXIMITY",
    "LIVE_LOW_BATTERY",
    "LIVE_TELEMETRY_LOSS",
]

SignalSeverity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
SignalPriority = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
SignalStatus = Literal["OPEN", "ACKNOWLEDGED", "IN_REVIEW", "RESOLVED", "DISMISSED"]


class SignalEvidenceRef(BaseModel):
    """Traceable provenance linking an intelligence signal directly back to underlying domain records."""

    source_type: str = Field(
        ...,
        description="Domain entity type: Flight, InspectionRequirement, MaintenanceRequirement, WorkOrder, Finding, Component, ComplianceObligation, EvidenceFile, Battery, AssetHistoricalBaseline",
    )
    source_id: str | None = Field(None, description="Primary key identifier of source domain object")
    label: str = Field(..., description="Human-readable domain label or title")
    metric: str | None = Field(None, description="Name of the tracked metric, e.g. flight_hours, cycles, days")
    current_value: Any | None = Field(None, description="Current recorded value")
    threshold_value: Any | None = Field(None, description="Operational or regulatory threshold value")
    details: str | None = Field(None, description="Additional context or excerpt from source record")


class SignalActionItem(BaseModel):
    """Actionable decision support item directing operator to next operational step."""

    action_type: str = Field(
        ...,
        description="Type: SCHEDULE_INSPECTION, CREATE_WORK_ORDER, ATTACH_EVIDENCE, REVIEW_FINDING, INSPECT_COMPONENT, VERIFY_COMPLIANCE, MONITOR_ASSET, ASK_LISA",
    )
    title: str = Field(..., description="Short button or headline text")
    description: str = Field(..., description="Action description and operational rationale")
    target_url: str | None = Field(None, description="Frontend navigation deep link")
    requires_authorization: bool = Field(True, description="Whether this operational action requires human sign-off")


class ProactiveSignalResponse(BaseModel):
    """Complete proactive intelligence signal record with full evidence and action items."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    signal_key: str
    signal_type: SignalType
    severity: SignalSeverity
    priority: SignalPriority
    status: SignalStatus

    title: str
    headline: str
    explanation: list[str]

    asset_id: uuid.UUID | None = None
    asset_registration: str | None = None
    asset_type: str | None = None
    component_id: uuid.UUID | None = None
    component_part_number: str | None = None

    detected_at: datetime
    evidence: list[SignalEvidenceRef] = []
    contributing_factors: dict[str, Any] = {}
    recommended_actions: list[SignalActionItem] = []

    acknowledged_by_user_id: uuid.UUID | None = None
    acknowledged_at: datetime | None = None

    resolved_by_user_id: uuid.UUID | None = None
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    dismissed_by_user_id: uuid.UUID | None = None
    dismissed_at: datetime | None = None
    dismissal_reason: str | None = None

    created_at: datetime
    updated_at: datetime | None = None


class SignalAcknowledgeRequest(BaseModel):
    """Operator acknowledgement of an intelligence signal."""

    notes: str | None = Field(None, description="Optional operator acknowledgement note")


class SignalInReviewRequest(BaseModel):
    """Transition signal to IN_REVIEW status."""

    notes: str | None = Field(None, description="Investigation notes")


class SignalResolveRequest(BaseModel):
    """Resolution of an intelligence signal following corrective action."""

    resolution_notes: str = Field(..., min_length=3, description="Explanation of corrective action or resolution")


class SignalDismissRequest(BaseModel):
    """Dismissal of an intelligence signal with justification."""

    dismissal_reason: str = Field(..., min_length=3, description="Operational justification for dismissal")


class ProactiveIntelligenceSummary(BaseModel):
    """Command Center Proactive Intelligence Overview."""

    total_active_signals: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    by_type: dict[str, int] = {}
    signals: list[ProactiveSignalResponse] = []
    emerging_risks: list[ProactiveSignalResponse] = []
    upcoming_thresholds: list[ProactiveSignalResponse] = []
    recurring_findings: list[ProactiveSignalResponse] = []
    compliance_evidence_gaps: list[ProactiveSignalResponse] = []
    readiness_changes: list[ProactiveSignalResponse] = []
    fleet_patterns: list[ProactiveSignalResponse] = []
    generated_at: datetime
