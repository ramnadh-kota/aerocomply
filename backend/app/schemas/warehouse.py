import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WarehouseCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)


class WarehouseResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class LocationCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    description: str | None = None


class LocationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    warehouse_id: uuid.UUID
    code: str
    description: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class PartLocationAssignRequest(BaseModel):
    location_id: uuid.UUID
