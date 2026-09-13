"""M5: request/response schemas for plan and plan-feature administration.

Mirrors the style of app/schemas/platform.py and app/schemas/entitlement.py --
pure serialization/validation shapes, no business logic. ORM objects
(``Plan``, ``PlanFeature``) are never returned directly from the API layer.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    description: str | None = None
    is_active: bool = True


class PlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlanFeatureCreateRequest(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    enabled: bool = True


class PlanFeatureUpdateRequest(BaseModel):
    enabled: bool


class PlanFeatureResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    feature_key: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
