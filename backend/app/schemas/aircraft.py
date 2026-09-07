import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AircraftCreateRequest(BaseModel):
    registration: str = Field(min_length=1, max_length=16)
    msn: str = Field(min_length=1, max_length=64)
    aircraft_type: str = Field(min_length=1, max_length=128)
    status: str = Field(default="ACTIVE", max_length=32)


class AircraftResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    registration: str
    msn: str
    aircraft_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
