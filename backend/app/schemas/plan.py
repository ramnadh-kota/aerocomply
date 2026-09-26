"""M5: request/response schemas for plan and plan-feature administration.

Mirrors the style of app/schemas/platform.py and app/schemas/entitlement.py --
pure serialization/validation shapes, no business logic. ORM objects
(``Plan``, ``PlanFeature``) are never returned directly from the API layer.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    description: str | None = None
    is_active: bool = True
    suite_id: uuid.UUID | None = None
    asset_scope: str | None = Field(default=None, max_length=32)


class PlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    suite_id: uuid.UUID | None = None
    asset_scope: str | None = Field(default=None, max_length=32)


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    description: str | None
    is_active: bool
    suite_id: uuid.UUID | None = None
    asset_scope: str | None = None
    included_features_count: int = 0
    tenant_count: int = 0
    created_at: datetime
    updated_at: datetime


class PlanFeatureCreateRequest(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    enabled: bool = True


class PlanFeatureUpdateRequest(BaseModel):
    enabled: bool


class PlanFeatureBulkItem(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    enabled: bool = True


class PlanFeatureBulkUpdateRequest(BaseModel):
    features: list[PlanFeatureBulkItem]


class PlanFeatureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    feature_key: str
    enabled: bool
    created_at: datetime
    updated_at: datetime



class PlanSubscribedTenantResponse(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    organization_status: str
    subscription_id: uuid.UUID
    subscription_status: str
    starts_at: datetime
    ends_at: datetime | None = None


class PlanLimitItem(BaseModel):
    limit_key: str = Field(min_length=1, max_length=128)
    limit_value: int | None = Field(default=None, ge=0)
    is_unlimited: bool = False

    @model_validator(mode="after")
    def validate_limits(self) -> "PlanLimitItem":
        if self.is_unlimited:
            self.limit_value = None
        elif self.limit_value is None:
            raise ValueError("limit_value is required when is_unlimited is False")
        return self


class PlanLimitBulkUpdateRequest(BaseModel):
    limits: list[PlanLimitItem]


class PlanLimitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    limit_key: str
    limit_value: int | None
    is_unlimited: bool
    created_at: datetime
    updated_at: datetime


