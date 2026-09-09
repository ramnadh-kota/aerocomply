import datetime
import uuid

from pydantic import BaseModel, Field


class PurchaseOrderLineCreateRequest(BaseModel):
    procurement_request_id: uuid.UUID | None = None
    part_number: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit_price_cents: int | None = Field(default=None, ge=0)


class PurchaseOrderCreateRequest(BaseModel):
    po_number: str = Field(min_length=1, max_length=64)
    vendor_id: uuid.UUID
    aircraft_id: uuid.UUID | None = None
    currency: str = Field(default="USD", max_length=8)
    tax_cents: int | None = Field(default=None, ge=0)
    shipping_cents: int | None = Field(default=None, ge=0)
    required_by: datetime.date | None = None
    notes: str | None = None
    lines: list[PurchaseOrderLineCreateRequest] = Field(min_length=1)


class PurchaseOrderLineResponse(BaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    procurement_request_id: uuid.UUID | None
    part_number: str
    description: str
    quantity: int
    unit_price_cents: int | None
    received_quantity: int

    class Config:
        from_attributes = True


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    po_number: str
    vendor_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    status: str
    currency: str
    subtotal_cents: int
    tax_cents: int | None
    shipping_cents: int | None
    total_cents: int
    required_by: datetime.date | None
    expected_delivery: datetime.date | None
    notes: str | None
    created_by_user_id: uuid.UUID | None
    approved_by_user_id: uuid.UUID | None
    lines: list[PurchaseOrderLineResponse]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class PurchaseOrderAcknowledgeRequest(BaseModel):
    expected_delivery: datetime.date | None = None
