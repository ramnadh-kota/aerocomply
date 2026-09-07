import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class InspectionRequirementCreateRequest(BaseModel):
    task_id: uuid.UUID | None = None
    work_order_id: uuid.UUID | None = None
    required: bool = True

    @model_validator(mode="after")
    def _require_task_or_work_order(self) -> "InspectionRequirementCreateRequest":
        if self.task_id is None and self.work_order_id is None:
            raise ValueError("Either task_id or work_order_id must be provided")
        return self


class InspectionTransitionRequest(BaseModel):
    target_status: str = Field(min_length=1, max_length=32)
    inspector_user_id: uuid.UUID | None = None
    rejection_reason: str | None = None


class InspectionRequirementResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    task_id: uuid.UUID | None
    work_order_id: uuid.UUID | None
    required: bool
    inspector_user_id: uuid.UUID | None
    status: str
    rejection_reason: str | None
    created_at: datetime

    class Config:
        from_attributes = True
