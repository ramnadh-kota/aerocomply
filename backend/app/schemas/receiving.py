import uuid

from pydantic import BaseModel, Field


class ReceiveLineRequest(BaseModel):
    line_id: uuid.UUID
    quantity: int = Field(gt=0)


class ReceivePurchaseOrderRequest(BaseModel):
    lines: list[ReceiveLineRequest] = Field(min_length=1)
    notes: str | None = None
