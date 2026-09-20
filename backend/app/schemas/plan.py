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
    # M21.4: which app.models.product_catalog.ProductSuite this plan is for
    # (optional -- see Plan.suite_id's docstring for why this is nullable
    # and single-valued).
    suite_id: uuid.UUID | None = None


class PlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    # M21.4. `...` (PydanticUndefined) sentinel isn't used here -- following
    # this file's existing convention (name/code/description above) of
    # "None means no change", which is why clearing suite_id back to
    # unassigned isn't supported through this endpoint; that's an accepted,
    # narrow limitation consistent with the rest of this schema, not an
    # oversight.
    suite_id: uuid.UUID | None = None


class PlanResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    description: str | None
    is_active: bool
    suite_id: uuid.UUID | None = None
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
