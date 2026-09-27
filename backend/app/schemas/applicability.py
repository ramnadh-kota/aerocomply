"""Pydantic schemas for the Applicability & Condition Tree engine."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApplicabilityConditionCreateRequest(BaseModel):
    condition_type: str = Field(
        ...,
        description="AIRCRAFT_VARIANT, MSN_RANGE, ENGINE_TYPE, AND, OR, or NOT",
    )
    label: str = Field(..., max_length=255)
    parameters: dict[str, Any] | None = None
    sequence: int = 0
    children: list["ApplicabilityConditionCreateRequest"] = Field(default_factory=list)


class ApplicabilityConditionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_id: uuid.UUID
    parent_condition_id: uuid.UUID | None = None
    condition_type: str
    label: str
    parameters: dict[str, Any] | None = None
    sequence: int = 0
    children: list["ApplicabilityConditionResponse"] = Field(default_factory=list)


class ApplicabilityRuleCreateRequest(BaseModel):
    rule_code: str = Field(..., max_length=64)
    title: str = Field(..., max_length=255)
    description: str | None = None
    regulatory_requirement_id: uuid.UUID | None = None
    is_active: bool = True
    root_condition: ApplicabilityConditionCreateRequest | None = None


class ApplicabilityRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    rule_code: str
    title: str
    description: str | None = None
    regulatory_requirement_id: uuid.UUID | None = None
    is_active: bool
    root_condition_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    conditions: list[ApplicabilityConditionResponse] = Field(default_factory=list)


class ApplicabilityEvaluationRequest(BaseModel):
    rule_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    notes: str | None = None
    force_review: bool = False

    @model_validator(mode="after")
    def validate_target(self) -> "ApplicabilityEvaluationRequest":
        if self.aircraft_id is None and self.asset_id is None:
            raise ValueError("Either aircraft_id or asset_id must be provided")
        return self


class ApplicabilityEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    rule_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    evaluated_by_user_id: uuid.UUID | None = None
    system_result: str
    evaluated_at: datetime
    configuration_snapshot: dict[str, Any]
    reasoning_trace: dict[str, Any]
    notes: str | None = None
