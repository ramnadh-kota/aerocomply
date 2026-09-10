import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PartCreateRequest(BaseModel):
    part_number: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)
    manufacturer: str | None = Field(default=None, max_length=255)
    condition: str | None = Field(default=None, max_length=32)
    serial_number: str | None = Field(default=None, max_length=128)
    batch_or_lot: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    quantity_on_hand: int = Field(default=0, ge=0)
    quantity_reserved: int = Field(default=0, ge=0)


class PartUpdateRequest(BaseModel):
    part_number: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, min_length=1)
    manufacturer: str | None = Field(default=None, max_length=255)
    condition: str | None = Field(default=None, max_length=32)
    serial_number: str | None = Field(default=None, max_length=128)
    batch_or_lot: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    quantity_on_hand: int | None = Field(default=None, ge=0)
    quantity_reserved: int | None = Field(default=None, ge=0)


class PartResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    part_number: str
    description: str
    manufacturer: str | None
    condition: str | None
    serial_number: str | None
    batch_or_lot: str | None
    location: str | None
    serviceability_status: str
    quarantine_reason: str | None
    quantity_on_hand: int
    quantity_reserved: int
    quantity_quarantined: int
    available_quantity: int
    created_at: datetime

    class Config:
        from_attributes = True
