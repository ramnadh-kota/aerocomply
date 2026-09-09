import uuid
from typing import Literal

from pydantic import BaseModel

BlockerCategory = Literal["EVIDENCE", "INSPECTION", "TASK_EXECUTION"]
ReadinessStatus = Literal["READY", "BLOCKED", "UNKNOWN"]


class Blocker(BaseModel):
    category: BlockerCategory
    description: str
    related_record_id: uuid.UUID


class ReleaseReadiness(BaseModel):
    work_order_id: uuid.UUID
    status: ReadinessStatus
    blockers: list[Blocker]
    data_completeness: str
