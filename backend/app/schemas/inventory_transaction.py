import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class InventoryReceiveRequest(BaseModel):
    quantity: int = Field(gt=0)
    reference_type: str | None = Field(default=None, max_length=32)
    reference_id: uuid.UUID | None = None
    notes: str | None = None


class InventoryReserveRequest(BaseModel):
    quantity: int = Field(gt=0)
    reference_type: str | None = Field(default=None, max_length=32)
    reference_id: uuid.UUID | None = None
    notes: str | None = None


class InventoryReleaseRequest(BaseModel):
    quantity: int = Field(gt=0)
    reference_type: str | None = Field(default=None, max_length=32)
    reference_id: uuid.UUID | None = None
    notes: str | None = None


class InventoryConsumeRequest(BaseModel):
    quantity: int = Field(gt=0)
    reference_type: str | None = Field(default=None, max_length=32)
    reference_id: uuid.UUID | None = None
    notes: str | None = None


class InventoryAdjustRequest(BaseModel):
    # Signed — positive for a found-stock correction, negative for a loss/damage
    # write-off. Zero is rejected in the model_validator below since it would be
    # a no-op transaction (Field(ne=0) is not supported for int in this Pydantic
    # version).
    on_hand_delta: int
    notes: str | None = None

    @field_validator("on_hand_delta")
    @classmethod
    def _reject_zero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("on_hand_delta must not be zero")
        return value


class InventoryQuarantineRequest(BaseModel):
    quantity: int = Field(gt=0)
    reason: str = Field(min_length=1)
    reference_type: str | None = Field(default=None, max_length=32)
    reference_id: uuid.UUID | None = None


class InventoryReleaseQuarantineRequest(BaseModel):
    quantity: int = Field(gt=0)
    # New status after release — SERVICEABLE (passed inspection) or SCRAPPED
    # (failed, being written off). Never defaults silently to SERVICEABLE.
    new_status: str = Field(max_length=32)
    notes: str | None = None


class InventoryTransactionResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    part_id: uuid.UUID
    transaction_type: str
    on_hand_delta: int
    reserved_delta: int
    quarantined_delta: int
    reference_type: str | None
    reference_id: uuid.UUID | None
    notes: str | None
    actor_user_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True
