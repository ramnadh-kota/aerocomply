import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FacilityCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    facility_type: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=2000)


class FacilityUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    facility_type: str | None = Field(default=None, min_length=1, max_length=32)
    status: str | None = Field(default=None, min_length=1, max_length=16)
    description: str | None = Field(default=None, max_length=2000)


class FacilityResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    name: str
    facility_type: str
    status: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
