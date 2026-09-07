import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    work_order_id: uuid.UUID
    description: str = Field(min_length=1)
    execution_state: str = Field(default="PENDING", max_length=32)


class TaskResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    work_order_id: uuid.UUID
    description: str
    execution_state: str
    created_at: datetime

    class Config:
        from_attributes = True
