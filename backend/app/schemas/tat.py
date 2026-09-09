import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel

TatStatusLiteral = Literal["ON_TRACK", "AT_RISK", "DELAYED", "UNKNOWN"]


class TatStatus(BaseModel):
    work_order_id: uuid.UUID
    status: TatStatusLiteral
    due_date: date | None
    days_remaining: int | None
    days_overdue: int | None
    reason: str


class FleetTatSummary(BaseModel):
    organization_id: uuid.UUID
    on_track_count: int
    at_risk_count: int
    delayed_count: int
    unknown_count: int
    total_work_orders: int
    reason: str
