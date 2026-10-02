"""C5: geofence API contracts. Geofences are ADVISORY operational zones, not legal airspace authorisation."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

GeofenceKind = Literal["RESTRICTED", "CAUTION", "OPERATING_AREA"]
GeometryType = Literal["CIRCLE", "POLYGON"]
AltitudeReference = Literal["MSL", "HOME_RELATIVE"]
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


class _GeofenceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    kind: GeofenceKind = Field(
        ..., description="RESTRICTED/CAUTION: entering is a violation. OPERATING_AREA: leaving is the violation."
    )
    geometry_type: GeometryType
    geometry: dict[str, Any] = Field(
        ...,
        description='CIRCLE {"center":{"lat","lon"},"radius_m"}; POLYGON {"ring":[[lon,lat],...]} (WGS84, GeoJSON order)',
    )
    altitude_reference: AltitudeReference = Field(
        "HOME_RELATIVE", description="HOME_RELATIVE is relative to the take-off point, NOT above ground level"
    )
    alt_min_m: float | None = Field(None, ge=-1000, le=100_000)
    alt_max_m: float | None = Field(None, ge=-1000, le=100_000)
    severity: Severity = "HIGH"
    proximity_buffer_m: float = Field(0.0, ge=0, le=50_000, description="0 disables proximity alerts")
    boundary_tolerance_m: float = Field(
        5.0, ge=0, le=1_000, description="Exit hysteresis band: a drone must be this far outside before it counts as out"
    )
    confirm_count: int = Field(2, ge=1, le=10, description="Consecutive reliable updates needed to change state")
    asset_ids: list[uuid.UUID] | None = Field(None, description="null = every drone of the organization")
    active_from: datetime | None = None
    active_until: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def _ranges(self):
        if self.alt_min_m is not None and self.alt_max_m is not None and self.alt_min_m >= self.alt_max_m:
            raise ValueError("alt_min_m must be below alt_max_m")
        if self.active_from and self.active_until and self.active_from >= self.active_until:
            raise ValueError("active_from must be before active_until")
        for dt in (self.active_from, self.active_until):
            if dt is not None and dt.tzinfo is None:
                raise ValueError("activation times must include a time zone")
        return self


class GeofenceCreate(_GeofenceFields):
    pass


class GeofenceUpdate(BaseModel):
    """Partial update. Changing geometry_type requires geometry in the same request."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2000)
    kind: GeofenceKind | None = None
    geometry_type: GeometryType | None = None
    geometry: dict[str, Any] | None = None
    altitude_reference: AltitudeReference | None = None
    alt_min_m: float | None = Field(None, ge=-1000, le=100_000)
    alt_max_m: float | None = Field(None, ge=-1000, le=100_000)
    severity: Severity | None = None
    proximity_buffer_m: float | None = Field(None, ge=0, le=50_000)
    boundary_tolerance_m: float | None = Field(None, ge=0, le=1_000)
    confirm_count: int | None = Field(None, ge=1, le=10)
    asset_ids: list[uuid.UUID] | None = None
    active_from: datetime | None = None
    active_until: datetime | None = None
    is_active: bool | None = None
    reason: str | None = Field(None, max_length=500, description="Recorded in the audit history")


class GeofenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    description: str | None
    kind: GeofenceKind
    geometry_type: GeometryType
    geometry: dict[str, Any]
    altitude_reference: AltitudeReference
    alt_min_m: float | None
    alt_max_m: float | None
    severity: Severity
    proximity_buffer_m: float
    boundary_tolerance_m: float
    confirm_count: int
    asset_ids: list[uuid.UUID] | None
    active_from: datetime | None
    active_until: datetime | None
    is_active: bool
    version: int
    advisory_notice: str = "Operational zone configured by the organization; not authoritative airspace authorisation."
    created_by_user_id: uuid.UUID | None
    updated_by_user_id: uuid.UUID | None
    created_at: datetime | None
    updated_at: datetime | None


class GeofenceVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    geofence_id: uuid.UUID
    version: int
    change_type: str
    snapshot: dict[str, Any]
    changed_by_user_id: uuid.UUID | None
    changed_at: datetime
