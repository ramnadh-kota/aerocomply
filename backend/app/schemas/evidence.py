import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceCreateRequest(BaseModel):
    task_id: uuid.UUID


class EvidenceTransitionRequest(BaseModel):
    target_status: str = Field(min_length=1, max_length=32)
    rejection_reason: str | None = None


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID | None
    status: str
    reviewer_user_id: uuid.UUID | None
    rejection_reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True
