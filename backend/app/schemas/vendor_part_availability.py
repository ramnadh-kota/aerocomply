import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VendorPartAvailabilityCreateRequest(BaseModel):
    vendor_id: uuid.UUID
    part_id: uuid.UUID
    availability_status: str = Field(default="UNKNOWN", max_length=32)
    quantity_available: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    unit_price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    aog_availability: bool | None = None
    certification_status: str = Field(default="UNKNOWN", max_length=32)


class VendorPartAvailabilityUpdateRequest(BaseModel):
    availability_status: str | None = Field(default=None, max_length=32)
    quantity_available: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    unit_price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    aog_availability: bool | None = None
    certification_status: str | None = Field(default=None, max_length=32)


class VendorPartAvailabilityResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    vendor_id: uuid.UUID
    part_id: uuid.UUID
    availability_status: str
    quantity_available: int | None
    lead_time_days: int | None
    unit_price_cents: int | None
    currency: str | None
    aog_availability: bool | None
    certification_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class VendorFitResult(BaseModel):
    vendor_id: uuid.UUID
    vendor_name: str
    availability: VendorPartAvailabilityResponse
    score: int | None
    confidence: str
    factors: list[str]
    missing_factors: list[str]
