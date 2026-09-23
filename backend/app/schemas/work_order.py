import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class WorkOrderCreateRequest(BaseModel):
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    work_order_number: str = Field(min_length=1, max_length=64)
    status: str = Field(default="OPEN", max_length=32)
    priority: str = Field(default="NORMAL", max_length=32)

    @model_validator(mode="after")
    def require_one_primary_asset(self) -> "WorkOrderCreateRequest":
        if (self.aircraft_id is None) == (self.asset_id is None):
            raise ValueError("Exactly one of aircraft_id or asset_id must be provided")
        return self


class WorkOrderResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    work_order_number: str
    status: str
    priority: str
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True
