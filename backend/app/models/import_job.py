"""Bulk data import job — the audit trail and staging record for the
CSV onboarding pipeline (validate -> preview -> confirm -> import).

Deliberately stores the validated row payload (JSON) on the job itself
rather than a separate table: import batches are onboarding-sized (dozens
to low thousands of rows), not a general-purpose data warehouse, and this
keeps "commit this job" a single, simple, transactional operation with no
extra table to keep in sync.
"""

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ImportDomain:
    AIRCRAFT = "AIRCRAFT"


class ImportJobStatus:
    VALIDATED = "VALIDATED"  # rows parsed/validated, awaiting confirm
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ImportJob(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "import_jobs"

    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ImportJobStatus.VALIDATED
    )
    created_by_user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=True)

    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_valid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_invalid: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Per-row validation results: [{row_number, status: VALID|INVALID|WARNING,
    # errors: [str], data: {...}}] — the source of truth the commit step
    # replays, and what the preview/error-report UI reads back.
    row_results: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["ImportJob", "ImportDomain", "ImportJobStatus"]
