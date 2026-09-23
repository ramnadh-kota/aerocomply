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
