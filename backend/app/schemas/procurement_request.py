import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProcurementRequestCreateRequest(BaseModel):
    aircraft_id: uuid.UUID
    work_order_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    part_id: uuid.UUID | None = None
    part_number: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)
    quantity: int = Field(default=1, gt=0)
    priority: str = Field(default="ROUTINE", max_length=16)
    reason: str = Field(min_length=1)
    preferred_vendor_id: uuid.UUID | None = None
    estimated_cost_cents: int | None = Field(default=None, ge=0)


class ProcurementRequestApproveRequest(BaseModel):
    selected_vendor_id: uuid.UUID | None = None


class ProcurementRequestRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=1)


class ProcurementRequestClarifyRequest(BaseModel):
    clarification_note: str = Field(min_length=1)


class ProcurementRequestResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID
    work_order_id: uuid.UUID | None
    task_id: uuid.UUID | None
    part_id: uuid.UUID | None
    part_number: str
    description: str
    quantity: int
    priority: str
    reason: str
    requested_by_user_id: uuid.UUID | None
    preferred_vendor_id: uuid.UUID | None
    selected_vendor_id: uuid.UUID | None
    status: str
    estimated_cost_cents: int | None
    approved_by_user_id: uuid.UUID | None
    rejection_reason: str | None
    clarification_note: str | None
    created_at: datetime

    class Config:
        from_attributes = True
