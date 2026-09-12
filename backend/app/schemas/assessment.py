import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AssessmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    scope_type: str = Field(default="FLEET", max_length=32)
    scope_id: uuid.UUID | None = None


class AssessmentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    scope_type: str
    scope_id: uuid.UUID | None
    status: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class AssessmentFindingResponse(BaseModel):
    id: uuid.UUID
    category: str
    severity: str
    title: str
    description: str
    entity_type: str
    entity_id: str
    materiality_score: float
    complexity_band: str
    dependency_count: int
    impact_dimensions: list[str]
    priority_rank: int
    source: str
    resolved: bool

    class Config:
        from_attributes = True


class AssessmentRiskResponse(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID | None
    risk_level: str
    likelihood: str
    reason: str
    entity_type: str
    entity_id: str
    mitigation: str | None
    owner_role: str | None

    class Config:
        from_attributes = True


class AssessmentGapResponse(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID | None
    category: str
    severity: str
    entity_type: str
    entity_id: str
    expected_condition: str
    current_condition: str
    recommended_action: str

    class Config:
        from_attributes = True


class AssessmentRecommendationResponse(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID | None
    recommendation: str
    why: str
    priority: str
    responsible_role: str | None
    entity_type: str
    entity_id: str
    status: str

    class Config:
        from_attributes = True


class AssessmentRoadmapItemResponse(BaseModel):
    id: uuid.UUID
    finding_id: uuid.UUID | None
    sequence: int
    title: str
    description: str
    category: str
    priority: str
    status: str
    entity_type: str
    entity_id: str
    prerequisite_sequence_numbers: list[int]
    owner_role: str | None
    estimated_effort_band: str
    effort_confidence: str
    expected_impact: str
    risk_if_delayed: str

    class Config:
        from_attributes = True


class AssessmentSnapshotResponse(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID
    version: int
    overall_score: float
    maturity_band: str
    summary: str | None
    finding_count: int
    critical_finding_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class AssessmentSnapshotComparisonResponse(BaseModel):
    from_version: int
    to_version: int
    score_delta: float
    new_findings: list[AssessmentFindingResponse]
    resolved_findings: list[str]
