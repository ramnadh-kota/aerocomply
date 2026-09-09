import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AogEventCreateRequest(BaseModel):
    aircraft_id: uuid.UUID
    work_order_id: uuid.UUID | None = None
    severity: str = Field(default="CRITICAL", max_length=16)
    root_cause: str | None = None


class AogBlockerCreateRequest(BaseModel):
    blocker_type: str = Field(max_length=32)
    description: str = Field(min_length=1)
    source_reference: str | None = Field(default=None, max_length=255)


class AogEventUpdateRequest(BaseModel):
    severity: str | None = Field(default=None, max_length=16)
    root_cause: str | None = None
    owner_user_id: uuid.UUID | None = None
    recovery_notes: str | None = None


class AogBlockerResponse(BaseModel):
    id: uuid.UUID
    aog_event_id: uuid.UUID
    blocker_type: str
    description: str
    source_reference: str | None
    resolved: bool

    class Config:
        from_attributes = True


class AogEventResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID
    work_order_id: uuid.UUID | None
    status: str
    severity: str
    root_cause: str | None
    declared_by_user_id: uuid.UUID | None
    owner_user_id: uuid.UUID | None
    recovery_notes: str | None
    blockers: list[AogBlockerResponse]
    created_at: datetime

    class Config:
        from_attributes = True
