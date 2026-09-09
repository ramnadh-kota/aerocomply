import datetime
import uuid

from pydantic import BaseModel, Field


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
    aircraft_id: uuid.UUID
    requirement_id: uuid.UUID
    status: str = Field(default="UNKNOWN", max_length=16)
    evaluated_at: datetime.date
    notes: str | None = None


class ComplianceAssessmentOverrideRequest(BaseModel):
    status: str = Field(max_length=16)
    override_reason: str = Field(min_length=1)


class ComplianceAssessmentResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID
    requirement_id: uuid.UUID
    status: str
    evaluated_at: datetime.date
    evaluated_by_user_id: uuid.UUID | None
    notes: str | None
    override_reason: str | None
    overridden_by_user_id: uuid.UUID | None

    class Config:
        from_attributes = True
