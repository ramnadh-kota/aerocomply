"""H7: MRO + Compliance + Readiness Intelligence Integration — schemas.

Stable contract for the H7 correlation layer. Every result here is a
CORRELATION over existing authoritative outputs (HUMS H1-H5,
aerospace_state_service, readiness_intelligence_service, maintenance,
compliance) -- never a new system of record. Fields follow the
DataAvailability convention from app/schemas/digital_twin.py: any
sub-state whose source data is missing is explicit (AVAILABLE /
DATA_UNAVAILABLE), never silently defaulted to a positive state.
"""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DataAvailability = Literal["AVAILABLE", "DATA_UNAVAILABLE"]

ReadinessImpactLevel = Literal[
    "NO_IMPACT",
    "MONITOR",
    "MAINTENANCE_DUE",
    "INSPECTION_REQUIRED",
    "REVIEW_REQUIRED",
    "RESTRICTED_OPERATION",
    "READINESS_AT_RISK",
    "UNKNOWN",
]

OperationalImpactLevel = Literal["LOW", "MEDIUM", "HIGH", "UNKNOWN"]

ComplianceImpactState = Literal[
    "COMPLIANT",
    "NON_COMPLIANT",
    "DUE",
    "OVERDUE",
    "UNKNOWN",
    "NOT_APPLICABLE",
    "REQUIRES_REVIEW",
]


class SourceLineageRef(BaseModel):
    """A pointer back to a source record -- ID/label only, never copied
    field data from the source entity."""

    source_type: str
    source_id: str | None = None
    label: str


class MaintenanceCandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    component_id: uuid.UUID | None
    candidate_type: str
    status: str
    priority: str
    confidence: float
    reason: str
    dedup_key: str
    source_lineage: list[dict[str, Any]]
    operational_impact: str | None
    data_freshness: str | None
    resolved_at: datetime | None
    resolved_by: uuid.UUID | None
    review_notes: str | None
    created_at: datetime
    updated_at: datetime


class CandidateActionRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class ComplianceImpactObligation(BaseModel):
    obligation_id: uuid.UUID
    requirement_id: uuid.UUID
    state: str  # verbatim ComplianceState.value from ComplianceObligation
    impact: ComplianceImpactState
    due_date: str | None = None
    correlated_signals: list[SourceLineageRef] = []
    explanation: list[str] = []


class ComplianceImpactResult(BaseModel):
    asset_id: uuid.UUID
    availability: DataAvailability
    obligations: list[ComplianceImpactObligation] = []
    overall_impact: ComplianceImpactState
    explanation: list[str] = []
    evaluated_at: datetime


class ReadinessImpactResult(BaseModel):
    """Carries BOTH the authoritative readiness_state (from
    readiness_intelligence_service, unmodified) and H7's own
    readiness_impact classification as separate fields. NEVER merge them --
    see this module's docstring and mro_intelligence_service's derivation
    docstring."""

    asset_id: uuid.UUID
    authoritative_readiness_state: Literal["READY", "BLOCKED", "UNKNOWN"]
    readiness_impact: ReadinessImpactLevel
    contributing_factors: list[SourceLineageRef] = []
    explanation: list[str] = []
    evaluated_at: datetime


class OperationalImpactResult(BaseModel):
    asset_id: uuid.UUID
    impact_level: OperationalImpactLevel
    reason: str
    contributing_factors: list[SourceLineageRef] = []
    evaluated_at: datetime


class IntegrationConflict(BaseModel):
    check: str
    description: str
    source_a: SourceLineageRef
    source_b: SourceLineageRef
    severity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"


class ReconciliationResult(BaseModel):
    asset_id: uuid.UUID
    resolved_candidate_ids: list[uuid.UUID] = []
    flagged_candidate_ids: list[uuid.UUID] = []
    explanation: list[str] = []
    evaluated_at: datetime


class AssetMROIntelligence(BaseModel):
    """Top-level H7 correlated view for one asset."""

    asset_id: uuid.UUID
    availability: DataAvailability
    health_state: str | None = None
    health_confidence: str | None = None
    open_diagnostic_count: int = 0
    open_prognostic_alert_count: int = 0
    authoritative_readiness_state: Literal["READY", "BLOCKED", "UNKNOWN"]
    readiness_impact: ReadinessImpactLevel
    compliance_impact: ComplianceImpactState
    operational_impact: OperationalImpactLevel
    open_candidate_count: int = 0
    candidates: list[MaintenanceCandidateOut] = []
    conflicts: list[IntegrationConflict] = []
    explanation: list[str] = []
    evaluated_at: datetime
