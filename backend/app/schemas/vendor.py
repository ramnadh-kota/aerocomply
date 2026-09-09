import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VendorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    certifications: str | None = None
    approved: bool = False
    reliability_score: int | None = Field(default=None, ge=0, le=100)


class VendorUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    certifications: str | None = None
    approved: bool | None = None
    reliability_score: int | None = Field(default=None, ge=0, le=100)


class VendorResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    contact_email: str | None
    location: str | None
    certifications: str | None
    approved: bool
    reliability_score: int | None
    created_at: datetime

    class Config:
        from_attributes = True
