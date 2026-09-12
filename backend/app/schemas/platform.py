import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrganizationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationAdminCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class PlatformOrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime
    user_count: int
    aircraft_count: int

    class Config:
        from_attributes = True
