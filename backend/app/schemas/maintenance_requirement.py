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


class MaintenanceAccomplishmentResponse(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    aircraft_id: uuid.UUID
    accomplished_at: datetime.date
    work_order_id: uuid.UUID | None
    notes: str | None

    class Config:
        from_attributes = True


class MaintenanceDueItem(BaseModel):
    requirement: MaintenanceRequirementResponse
    aircraft_id: uuid.UUID
    last_accomplished_at: datetime.date | None
    due_status: str  # OVERDUE | DUE_SOON | NOT_DUE | UNKNOWN
    due_date: datetime.date | None
    reason: str
