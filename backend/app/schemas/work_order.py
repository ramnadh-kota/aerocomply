import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# Fixed reason-code vocabularies for the WorkOrder lifecycle (Phase 3):
# deliberately closed sets, not arbitrary strings, so a reason is always
# machine-readable. No database column stores these -- they live only in
# the work_order.deleted/work_order.restored audit event's metadata (see
# app/services/audit_service.record_audit_event's metadata parameter).
WorkOrderDeleteReasonCode = Literal[
    "CREATED_IN_ERROR",
    "DUPLICATE_WORK_ORDER",
    "INCORRECT_ASSET",
    "ADMINISTRATIVE_CORRECTION",
    "OTHER",
]
WorkOrderRestoreReasonCode = Literal[
    "DELETED_IN_ERROR",
    "OPERATIONAL_REQUIREMENT",
    "ADMINISTRATIVE_CORRECTION",
    "OTHER",
]


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


class WorkOrderDeleteRequest(BaseModel):
    reason_code: WorkOrderDeleteReasonCode
    note: str | None = Field(default=None, max_length=1000)


class WorkOrderRestoreRequest(BaseModel):
    reason_code: WorkOrderRestoreReasonCode
    note: str | None = Field(default=None, max_length=1000)


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
