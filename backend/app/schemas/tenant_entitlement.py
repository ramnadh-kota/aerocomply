"""M6: request/response schemas for tenant feature-override and usage-limit
administration."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TenantFeatureOverrideCreateRequest(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    enabled: bool
    reason: str | None = None
    expires_at: datetime | None = None


class TenantFeatureOverrideUpdateRequest(BaseModel):
    enabled: bool | None = None
    reason: str | None = None
    expires_at: datetime | None = None


class TenantFeatureOverrideResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    feature_key: str
    enabled: bool
    reason: str | None
    expires_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class TenantUsageLimitCreateRequest(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    limit_key: str = Field(min_length=1, max_length=128)
    limit_value: int | None = None
    is_unlimited: bool = False


class TenantUsageLimitUpdateRequest(BaseModel):
    limit_value: int | None = None
    is_unlimited: bool | None = None


class TenantUsageLimitResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    feature_key: str
    limit_key: str
    limit_value: int | None
    is_unlimited: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
