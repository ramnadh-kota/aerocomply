import datetime
import uuid

from pydantic import BaseModel, Field, model_validator


class RegulatoryRequirementCreateRequest(BaseModel):
    authority: str = Field(max_length=16)
    regulatory_document_id: uuid.UUID | None = None
    requirement_number: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    effective_date: datetime.date | None = None
    compliance_time: str | None = Field(default=None, max_length=255)
    source_url: str | None = Field(default=None, max_length=512)


class RegulatoryRequirementResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    authority: str
    regulatory_document_id: uuid.UUID | None
    requirement_number: str
    title: str
    description: str
    effective_date: datetime.date | None
    compliance_time: str | None
    source_url: str | None

    class Config:
        from_attributes = True


class ComplianceAssessmentCreateRequest(BaseModel):
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    requirement_id: uuid.UUID
    status: str = Field(default="UNKNOWN", max_length=16)
    evaluated_at: datetime.date
    notes: str | None = None

    @model_validator(mode="after")
    def validate_subject(self) -> "ComplianceAssessmentCreateRequest":
        if self.aircraft_id is None and self.asset_id is None:
            raise ValueError("At least one of aircraft_id or asset_id must be provided")
        return self


class ComplianceAssessmentOverrideRequest(BaseModel):
    status: str = Field(max_length=16)
    override_reason: str = Field(min_length=1)


class ComplianceAssessmentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    requirement_id: uuid.UUID
    status: str
    evaluated_at: datetime.date
    evaluated_by_user_id: uuid.UUID | None
    notes: str | None
    override_reason: str | None
    overridden_by_user_id: uuid.UUID | None

    class Config:
        from_attributes = True


class ComplianceObligationCreateRequest(BaseModel):
    requirement_id: uuid.UUID
    rule_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    applicability_evaluation_id: uuid.UUID | None = None
    priority: str = Field(default="MEDIUM", max_length=32)
    due_date: datetime.date | None = None
    recurrence: str | None = Field(default=None, max_length=64)
    responsible_role: str | None = Field(default=None, max_length=64)
    assigned_user_id: uuid.UUID | None = None
    required_action: str | None = None
    evidence_requirements: list[dict] | dict | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ComplianceObligationCreateRequest":
        if self.aircraft_id is None and self.asset_id is None:
            raise ValueError("At least one of aircraft_id or asset_id must be provided")
        return self


class ComplianceObligationUpdateRequest(BaseModel):
    status: str | None = Field(default=None, max_length=32)
    priority: str | None = Field(default=None, max_length=32)
    due_date: datetime.date | None = None
    recurrence: str | None = Field(default=None, max_length=64)
    responsible_role: str | None = Field(default=None, max_length=64)
    assigned_user_id: uuid.UUID | None = None
    required_action: str | None = None
    evidence_requirements: list[dict] | dict | None = None
    notes: str | None = None


class ComplianceObligationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    requirement_id: uuid.UUID
    rule_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    aircraft_id: uuid.UUID | None = None
    applicability_evaluation_id: uuid.UUID | None = None
    status: str
    priority: str
    due_date: datetime.date | None = None
    recurrence: str | None = None
    responsible_role: str | None = None
    assigned_user_id: uuid.UUID | None = None
    required_action: str | None = None
    evidence_requirements: list[dict] | dict | None = None
    completed_at: datetime.datetime | None = None
    verified_at: datetime.datetime | None = None
    notes: str | None = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class ComplianceTraceabilityResponse(BaseModel):
    obligation_id: uuid.UUID
    compliance_state: str
    is_compliant: bool
    requirement: dict
    asset: dict
    why_applies: dict
    required_action: dict
    required_evidence: list[dict]
    provided_evidence: list[dict]
    is_verified: bool
    blockers: list[str]


class ComplianceOverviewResponse(BaseModel):
    total_obligations: int
    applicable_count: int
    compliant_count: int
    due_count: int
    overdue_count: int
    in_progress_count: int
    non_compliant_count: int
    blocked_count: int
    review_required_count: int
    not_applicable_count: int
    compliance_rate_percent: float

