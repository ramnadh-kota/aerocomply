"""Compliance Intelligence Schemas.

Domain schemas for:
- Inspection intelligence
- Finding correlation
- Authoritative Compliance Readiness Contribution
- Deep traceability and blocker explanation
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ComplianceReadinessBlocker(BaseModel):
    """Authoritative compliance/inspection blocker for operational readiness gates."""

    blocker_id: str
    category: str  # NON_COMPLIANT_OBLIGATION, OVERDUE_OBLIGATION, CRITICAL_FINDING, MISSING_EVIDENCE, REJECTED_EVIDENCE, FAILED_INSPECTION, INSUFFICIENT_DATA, REVIEW_REQUIRED
    what_blocking: str
    why_blocking: str
    source_record_type: str  # ComplianceObligation, Finding, Evidence, InspectionRequirement, ApplicabilityEvaluation
    source_record_id: uuid.UUID
    regulatory_requirement_number: str | None = None
    regulatory_requirement_title: str | None = None
    required_action: str | None = None
    missing_evidence: str | None = None
    resolution_action: str


class ComplianceReadinessContribution(BaseModel):
    """Authoritative compliance readiness contribution exposed to Developer 1's readiness gate system."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    overall_status: str  # READY | BLOCKED | REVIEW_REQUIRED | UNKNOWN
    blockers: list[ComplianceReadinessBlocker] = []
    warnings: list[str] = []
    compliance_obligations_count: int = 0
    compliant_obligations_count: int = 0
    overdue_obligations_count: int = 0
    critical_findings_count: int = 0
    missing_evidence_count: int = 0
    rejected_evidence_count: int = 0
    review_required_count: int = 0
    source_records: list[dict[str, Any]] = []
    evaluated_at: datetime


class FindingComplianceImpactResponse(BaseModel):
    """Compliance and readiness impact analysis of an inspection finding."""

    model_config = ConfigDict(from_attributes=True)

    finding_id: uuid.UUID
    title: str
    severity: str
    status: str
    safety_significance: str | None = None
    compliance_relevance: str | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    inspection_requirement_id: uuid.UUID | None = None
    compliance_obligation_id: uuid.UUID | None = None
    regulatory_requirement_id: uuid.UUID | None = None
    regulatory_requirement_number: str | None = None
    regulatory_requirement_title: str | None = None
    current_compliance_state: str | None = None
    corrective_action_required: str | None = None
    evidence_status: str | None = None
    evidence_verification_status: str | None = None
    is_readiness_blocker: bool = False
    blocker_reason: str | None = None


class InspectionComplianceImpactResponse(BaseModel):
    """Compliance and readiness impact analysis of an inspection requirement."""

    model_config = ConfigDict(from_attributes=True)

    inspection_requirement_id: uuid.UUID
    status: str
    required: bool
    inspector_user_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    compliance_obligation_id: uuid.UUID | None = None
    regulatory_requirement_id: uuid.UUID | None = None
    regulatory_requirement_number: str | None = None
    current_compliance_state: str | None = None
    associated_findings: list[dict[str, Any]] = []
    attached_evidence: list[dict[str, Any]] = []
    is_readiness_blocker: bool = False
    blocker_reason: str | None = None


class AssetComplianceImpactResponse(BaseModel):
    """Full asset-level compliance impact report connecting all domain threads."""

    model_config = ConfigDict(from_attributes=True)

    asset_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    overall_status: str
    readiness_contribution: ComplianceReadinessContribution
    active_blockers: list[ComplianceReadinessBlocker] = []
    critical_findings: list[FindingComplianceImpactResponse] = []
    overdue_obligations: list[dict[str, Any]] = []
    missing_or_rejected_evidence: list[dict[str, Any]] = []
    inspections_requiring_action: list[InspectionComplianceImpactResponse] = []
