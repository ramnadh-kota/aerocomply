import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TechnicianQualificationCreateRequest(BaseModel):
    user_id: uuid.UUID
    aircraft_type: str = Field(min_length=1, max_length=128)
    qualification_type: str = Field(min_length=1, max_length=64)
    granted_at: datetime | None = None
    expires_at: datetime | None = None


class TechnicianQualificationResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    aircraft_type: str
    qualification_type: str
    granted_at: datetime
    expires_at: datetime | None
    revoked: bool
    granted_by_user_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class AssignTechnicianRequest(BaseModel):
    technician_user_id: uuid.UUID


class TechnicianAuthorizationResponse(BaseModel):
    status: str  # AUTHORIZED | NOT_AUTHORIZED | EXPIRED | MISSING | UNKNOWN
    reason: str
    task_id: uuid.UUID
    technician_user_id: uuid.UUID
    aircraft_type: str | None
    qualification_id: uuid.UUID | None
