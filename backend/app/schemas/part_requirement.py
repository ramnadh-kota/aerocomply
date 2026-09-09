import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PartRequirementCreateRequest(BaseModel):
    work_order_id: uuid.UUID
    task_id: uuid.UUID | None = None
    part_id: uuid.UUID
    required_quantity: int = Field(default=1, ge=1)
    priority: str = Field(default="NORMAL", max_length=32)


class PartRequirementUpdateRequest(BaseModel):
    required_quantity: int | None = Field(default=None, ge=1)
    fulfilled_quantity: int | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, max_length=32)
    priority: str | None = Field(default=None, max_length=32)


class PartRequirementResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    work_order_id: uuid.UUID
    task_id: uuid.UUID | None
    part_id: uuid.UUID
    required_quantity: int
    fulfilled_quantity: int
    status: str
    priority: str
    created_at: datetime

    class Config:
        from_attributes = True
