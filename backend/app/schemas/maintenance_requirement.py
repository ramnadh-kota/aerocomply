import datetime
import uuid

from pydantic import BaseModel, Field


class MaintenanceRequirementCreateRequest(BaseModel):
    description: str = Field(min_length=1)
    ata_chapter: str = Field(min_length=1, max_length=16)
    interval_type: str = Field(max_length=16)
    fh_interval: int | None = Field(default=None, gt=0)
    fc_interval: int | None = Field(default=None, gt=0)
    calendar_interval_days: int | None = Field(default=None, gt=0)
    task_reference: str | None = Field(default=None, max_length=64)


class MaintenanceRequirementResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    description: str
    ata_chapter: str
    interval_type: str
    fh_interval: int | None
    fc_interval: int | None
    calendar_interval_days: int | None
    task_reference: str | None

    class Config:
        from_attributes = True


class MaintenanceApplicabilityCreateRequest(BaseModel):
    aircraft_id: uuid.UUID


class MaintenanceAccomplishmentCreateRequest(BaseModel):
    aircraft_id: uuid.UUID
    accomplished_at: datetime.date
    work_order_id: uuid.UUID | None = None
    notes: str | None = None


# M17.4A: asset(Drone)-scoped counterparts of the two request bodies above.
# asset_id always comes from the URL path (see app/api/v1/drones.py), never
# from the request body -- same convention as every other asset-scoped
# write in this codebase.


class AssetMaintenanceAccomplishmentCreateRequest(BaseModel):
    accomplished_at: datetime.date
    work_order_id: uuid.UUID | None = None
    notes: str | None = None


class MaintenanceAccomplishmentResponse(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    battery_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    accomplished_at: datetime.date
    work_order_id: uuid.UUID | None
    notes: str | None

    class Config:
        from_attributes = True


class MaintenanceDueItem(BaseModel):
    requirement: MaintenanceRequirementResponse
    # Exactly one of these four is set, matching
    # MaintenanceRequirementApplicability/MaintenanceAccomplishment's own
    # nullable aircraft_id/asset_id/battery_id/component_id columns --
    # never more than one, never none.
    aircraft_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    battery_id: uuid.UUID | None = None
    component_id: uuid.UUID | None = None
    last_accomplished_at: datetime.date | None
    due_status: str  # OVERDUE | DUE_SOON | NOT_DUE | UNKNOWN
    due_date: datetime.date | None
    reason: str
    # M17.4B: only set for a usage-based (FLIGHT_HOURS/FLIGHT_CYCLES/
    # BATTERY_CYCLES/COMPONENT_HOURS/COMPONENT_CYCLES) requirement; None for
    # CALENDAR (whose due_date above is the authoritative figure) or when
    # usage cannot yet be computed. current_usage is usage SINCE the last
    # accomplishment (what due_status is computed from); lifetime_usage
    # (M17.5B) is the item's total usage ever, which a maintenance
    # accomplishment never resets -- the two are deliberately different
    # numbers (see maintenance_service.py's module docstring).
    current_usage: float | None = None
    remaining_usage: float | None = None
    lifetime_usage: float | None = None
