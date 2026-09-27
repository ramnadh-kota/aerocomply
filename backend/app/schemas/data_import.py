import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImportRowResult(BaseModel):
    row_number: int
    status: str  # VALID | INVALID | WARNING
    errors: list[str] = []
    warnings: list[str] = []
    data: dict[str, Any] = {}
    matched_asset_id: str | None = None
    match_action: str | None = None  # MATCH_EXISTING | CREATE_ASSET | SKIP


class ImportJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    domain: str
    filename: str
    file_hash: str | None = None
    status: str
    sheet_names: list[str] | None = None
    selected_sheet: str | None = None
    column_mapping: dict[str, str] | None = None
    rows_total: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    warning_count: int = 0
    error_count: int = 0
    rows_created: int = 0
    rows_updated: int = 0
    rows_failed: int = 0
    error_summary: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ImportJobDetailResponse(ImportJobResponse):
    row_results: list[ImportRowResult] = []
    unmatched_assets: list[str] = []


class ImportConfigureRequest(BaseModel):
    selected_sheet: str | None = None
    column_mapping: dict[str, str] | None = None
    match_strategy: dict[str, str] | None = None  # e.g. {"VT-NEW": "CREATE_ASSET", "VT-XYZ": "MATCH_EXISTING"}


class ImportMappingCreateRequest(BaseModel):
    domain: str = Field(max_length=64)
    name: str = Field(max_length=255)
    mapping: dict[str, str] = Field(description="Dictionary mapping source header to canonical field name")
    is_default: bool = False


class ImportMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    domain: str
    name: str
    mapping: dict[str, str]
    is_default: bool
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
