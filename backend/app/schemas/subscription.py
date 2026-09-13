"""M6: request/response schemas for subscription administration. Mirrors
app/schemas/plan.py's style -- pure serialization/validation, no business
logic."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SubscriptionCreateRequest(BaseModel):
    plan_id: uuid.UUID
    status: str = Field(min_length=1, max_length=16)
    starts_at: datetime
    ends_at: datetime | None = None


class SubscriptionScheduleRequest(BaseModel):
    plan_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime | None = None


class SubscriptionUpdateRequest(BaseModel):
    status: str | None = Field(default=None, min_length=1, max_length=16)
    plan_id: uuid.UUID | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    plan_id: uuid.UUID
    status: str
    starts_at: datetime
    ends_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
