import datetime
import uuid

from pydantic import BaseModel


class ProactiveAlert(BaseModel):
    id: str
    category: str  # AOG | PART_SHORTAGE | RELEASE_BLOCKER | DEFERRED_MEL | COMPLIANCE
    severity: str  # CRITICAL | HIGH | MEDIUM
    title: str
    message: str
    source_type: str
    source_id: uuid.UUID
    aircraft_id: uuid.UUID | None
    work_order_id: uuid.UUID | None = None


class DailyBrief(BaseModel):
    generated_at: datetime.datetime
    critical_count: int
    high_count: int
    medium_count: int
    total_count: int
    top_priorities: list[ProactiveAlert]
    not_implemented: list[str]
