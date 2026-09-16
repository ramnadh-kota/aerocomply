import uuid
from datetime import datetime

from pydantic import BaseModel


class AssetResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    asset_type: str
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    registration: str | None
    status: str
    acquired_at: datetime | None
    retired_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True
