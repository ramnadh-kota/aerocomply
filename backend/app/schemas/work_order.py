import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class WorkOrderCreateRequest(BaseModel):
    aircraft_id: uuid.UUID
    work_order_number: str = Field(min_length=1, max_length=64)
    status: str = Field(default="OPEN", max_length=32)
    priority: str = Field(default="NORMAL", max_length=32)


class WorkOrderResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID
    work_order_number: str
    status: str
    priority: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True
