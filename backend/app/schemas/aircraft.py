import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AircraftCreateRequest(BaseModel):
    registration: str = Field(min_length=1, max_length=16)
    msn: str = Field(min_length=1, max_length=64)
    aircraft_type: str = Field(min_length=1, max_length=128)
    status: str = Field(default="ACTIVE", max_length=32)
    # Optional: not part of the Aircraft/AircraftDetail tables (they have no
    # meaningful "manufacturer" column of their own -- aircraft_type already
    # carries the type designation, e.g. "A320"), but Asset.manufacturer is a
    # real, existing column on the generic Asset row this creates alongside
    # Aircraft. Without this, an Aircraft-typed Asset would always have a
    # null manufacturer even when the caller has the data, unlike every
    # other asset type created through POST /assets.
    manufacturer: str | None = Field(default=None, max_length=128)


class AircraftUpdateRequest(BaseModel):
    """Fields intentionally excluded: registration (immutable once created,
    same precedent as the generic Asset foundation's AssetUpdateRequest --
    see app/schemas/asset.py)."""

    manufacturer: str | None = Field(default=None, max_length=128)
    msn: str | None = Field(default=None, min_length=1, max_length=64)
    aircraft_type: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = Field(default=None, max_length=32)


class AircraftResponse(BaseModel):
    # asset_id is deliberately NOT exposed here -- a dedicated backward-
    # compatibility test (TestAircraftApiResponseBackwardCompatibility in
    # tests/integration/test_asset_foundation.py) asserts this response
    # shape is exactly unchanged by the Asset/AircraftDetail dual-write.
    id: uuid.UUID
    organization_id: uuid.UUID
    registration: str
    msn: str
    aircraft_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
