import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorkOrderCreateRequest(BaseModel):
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    work_order_number: str = Field(min_length=1, max_length=64)
    title: str = Field(default="Untitled Work Order", max_length=255)
    description: str | None = None
    work_order_type: str = Field(default="CORRECTIVE", max_length=64)
    maintenance_category: str | None = None
    status: str = Field(default="DRAFT", max_length=32)
    priority: str = Field(default="NORMAL", max_length=32)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    due_at: datetime | None = None
    estimated_hours: float | None = None
    estimated_cost: float | None = None
    assigned_to_user_id: uuid.UUID | None = None
    location: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    compliance_required: bool = False
    compliance_reference: str | None = None

    @model_validator(mode="after")
    def require_one_primary_asset(self) -> "WorkOrderCreateRequest":
        if (self.aircraft_id is None) == (self.asset_id is None):
            raise ValueError("Exactly one of aircraft_id or asset_id must be provided")
        return self


class WorkOrderUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    work_order_type: str | None = Field(default=None, max_length=64)
    maintenance_category: str | None = None
    priority: str | None = Field(default=None, max_length=32)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    due_at: datetime | None = None
    estimated_hours: float | None = None
    actual_hours: float | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    location: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    compliance_required: bool | None = None
    compliance_reference: str | None = None


class WorkOrderAssignRequest(BaseModel):
    assigned_to_user_id: uuid.UUID


class WorkOrderTransitionRequest(BaseModel):
    target_status: str = Field(min_length=1, max_length=32)
    notes: str | None = None
    reason: str | None = None


class WorkOrderCancelRequest(BaseModel):
    cancellation_reason: str | None = Field(default=None, max_length=500)
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_reason(self) -> "WorkOrderCancelRequest":
        val = self.cancellation_reason or self.reason
        if not val or len(val.strip()) < 3:
            raise ValueError("Cancellation reason must be at least 3 characters.")
        self.cancellation_reason = val.strip()
        self.reason = val.strip()
        return self


class WorkOrderResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    work_order_number: str
    title: str
    description: str | None
    work_order_type: str
    maintenance_category: str | None
    status: str
    priority: str
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    due_at: datetime | None
    estimated_hours: float | None
    actual_hours: float | None
    estimated_cost: float | None
    actual_cost: float | None
    assigned_to_user_id: uuid.UUID | None
    location: str | None
    source_type: str | None
    source_reference: str | None
    compliance_required: bool
    compliance_reference: str | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkOrderListResponse(BaseModel):
    items: list[WorkOrderResponse]
    total: int
    limit: int
    offset: int
