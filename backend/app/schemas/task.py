import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCreateRequest(BaseModel):
    work_order_id: uuid.UUID | None = None
    task_number: str | None = Field(default=None, max_length=32)
    title: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=1)
    execution_state: str = Field(default="PENDING", max_length=32)
    assigned_technician_user_id: uuid.UUID | None = None
    estimated_hours: float | None = None
    sequence: int = 1
    evidence_required: bool = False
    notes: str | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    assigned_technician_user_id: uuid.UUID | None = None
    estimated_hours: float | None = None
    actual_hours: float | None = None
    sequence: int | None = None
    evidence_required: bool | None = None
    notes: str | None = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    work_order_id: uuid.UUID
    task_number: str | None = None
    title: str | None = None
    description: str
    execution_state: str
    assigned_technician_user_id: uuid.UUID | None
    evidence_required: bool = False
    estimated_hours: float | None = None
    actual_hours: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    sequence: int = 1
    notes: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
