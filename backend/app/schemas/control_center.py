import uuid

from pydantic import BaseModel


class ControlCenterAircraftRow(BaseModel):
    aircraft_id: uuid.UUID
    registration: str
    operational_status: str  # OPERATIONAL | UNDER_MAINTENANCE | AOG
    open_work_orders: int
    open_deferred_items: int
    open_part_shortages: int
    active_aog_event_id: uuid.UUID | None


class ControlCenterSummary(BaseModel):
    total_aircraft: int
    operational: int
    under_maintenance: int
    aog: int
    open_work_orders_total: int
    open_deferred_items_total: int
    open_part_shortages_total: int
