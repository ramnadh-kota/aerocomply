import datetime
import uuid

from pydantic import BaseModel, Field


class MissionCreateRequest(BaseModel):
    asset_id: uuid.UUID
    pilot_user_id: uuid.UUID | None = None
    purpose: str = Field(min_length=1, max_length=255)
    operating_area: str | None = Field(default=None, max_length=255)
    planned_start: datetime.datetime | None = None
    planned_end: datetime.datetime | None = None
    notes: str | None = None


class MissionUpdateRequest(BaseModel):
    pilot_user_id: uuid.UUID | None = None
    purpose: str | None = Field(default=None, min_length=1, max_length=255)
    operating_area: str | None = Field(default=None, max_length=255)
    planned_start: datetime.datetime | None = None
    planned_end: datetime.datetime | None = None
    status: str | None = Field(default=None, max_length=32)
    notes: str | None = None


class MissionAuthorizeRequest(BaseModel):
    notes: str | None = None


class MissionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID
    pilot_user_id: uuid.UUID | None
    status: str
    purpose: str
    operating_area: str | None
    planned_start: datetime.datetime | None
    planned_end: datetime.datetime | None
    authorized_at: datetime.datetime | None
    authorized_by_user_id: uuid.UUID | None
    notes: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class MissionListResponse(BaseModel):
    items: list[MissionResponse]
    total: int
    limit: int
    offset: int
