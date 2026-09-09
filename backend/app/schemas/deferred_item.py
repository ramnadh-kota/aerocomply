import datetime
import uuid

from pydantic import BaseModel, Field


class DeferredItemCreateRequest(BaseModel):
    aircraft_id: uuid.UUID
    work_order_id: uuid.UUID | None = None
    mel_reference: str | None = Field(default=None, max_length=64)
    category: str = Field(default="UNKNOWN", max_length=16)
    description: str = Field(min_length=1)
    opened_at: datetime.date
    due_at: datetime.date | None = None
    deferral_basis: str = Field(default="UNKNOWN", max_length=16)
    operational_limitations: str | None = None
    required_actions: str | None = None
    approval_required: bool = False


class DeferredItemUpdateRequest(BaseModel):
    mel_reference: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=16)
    due_at: datetime.date | None = None
    deferral_basis: str | None = Field(default=None, max_length=16)
    operational_limitations: str | None = None
    required_actions: str | None = None
    approval_status: str | None = Field(default=None, max_length=16)


class DeferredItemCloseRequest(BaseModel):
    closed_at: datetime.date
    closure_notes: str | None = None


class DeferredItemResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    aircraft_id: uuid.UUID
    work_order_id: uuid.UUID | None
    mel_reference: str | None
    category: str
    description: str
    opened_at: datetime.date
    due_at: datetime.date | None
    status: str
    deferral_basis: str
    operational_limitations: str | None
    required_actions: str | None
    approval_required: bool
    approval_status: str
    closed_at: datetime.date | None
    closure_notes: str | None

    class Config:
        from_attributes = True
