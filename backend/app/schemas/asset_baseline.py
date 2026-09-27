import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetHistoricalBaselineCreateRequest(BaseModel):
    flight_hours: float = Field(ge=0.0, description="Cumulative airframe flight hours at baseline point")
    flight_cycles: int = Field(default=0, ge=0, description="Cumulative flight cycles at baseline point")
    effective_at: datetime = Field(description="Authoritative effective date/time of carry-in totals")
    source: str = Field(default="MANUAL", max_length=64, description="Source system e.g. MIGRATION, EXCEL, MANUAL")
    evidence_reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class AssetHistoricalBaselineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    asset_id: uuid.UUID
    flight_hours: float
    flight_cycles: int
    effective_at: datetime
    source: str
    evidence_reference: str | None = None
    notes: str | None = None
    created_by_user_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
