import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ImportRowResult(BaseModel):
    row_number: int
    status: str  # VALID | INVALID | WARNING
    errors: list[str]
    warnings: list[str]
    data: dict[str, Any]


class ImportJobResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    domain: str
    filename: str
    status: str
    rows_total: int
    rows_valid: int
    rows_invalid: int
    rows_created: int
    rows_updated: int
    rows_failed: int
    error_summary: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ImportJobDetailResponse(ImportJobResponse):
    row_results: list[ImportRowResult]
