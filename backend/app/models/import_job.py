"""Bulk data import job — the audit trail and staging record for the
CSV onboarding pipeline (validate -> preview -> confirm -> import).

Deliberately stores the validated row payload (JSON) on the job itself
rather than a separate table: import batches are onboarding-sized (dozens
to low thousands of rows), not a general-purpose data warehouse, and this
keeps "commit this job" a single, simple, transactional operation with no
extra table to keep in sync.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ImportDomain:
    AIRCRAFT = "AIRCRAFT"
    DRONE = "DRONE"
    FLIGHT = "FLIGHT"


class ImportJobStatus:
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    MAPPED = "MAPPED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    STAGED = "STAGED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    IMPORTING = "IMPORTING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ImportJob(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"

    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ImportJobStatus.VALIDATED, index=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=True)

    sheet_names: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    selected_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    column_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    match_strategy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Per-row validation results: [{row_number, status: VALID|INVALID|WARNING,
    # errors: [str], warnings: [str], data: {...}, matched_asset_id: str | None,
    # match_action: MATCH_EXISTING|CREATE_ASSET|SKIP}]
    row_results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


__all__ = ["ImportJob", "ImportDomain", "ImportJobStatus"]
