"""Durable background jobs (PostgreSQL-backed queue).

One table, claimed with `SELECT ... FOR UPDATE SKIP LOCKED`, so no extra infrastructure is needed and a job is
committed in the same database as the data it produces. Scaling path: the `job_service` interface (enqueue/claim/
complete/fail) can be re-backed by Redis/SQS/Kafka without touching handlers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class JobStatus:
    QUEUED = "QUEUED"        # waiting (also: waiting for retry backoff, see run_after)
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    DEAD = "DEAD"            # dead-letter: attempts exhausted or non-retryable failure; needs an operator
    CANCELED = "CANCELED"
    ALL = frozenset({QUEUED, RUNNING, SUCCEEDED, DEAD, CANCELED})


class BackgroundJob(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','DEAD','CANCELED')", name="ck_background_jobs_status"
        ),
        UniqueConstraint("job_type", "dedupe_key", name="uq_background_jobs_type_dedupe"),
        Index("ix_background_jobs_claim", "status", "run_after"),
        Index("ix_background_jobs_org_status", "organization_id", "status"),
    )

    # NULL only for platform-level jobs (retention sweep, etc.); tenant jobs always carry their organization.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    data_source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.QUEUED)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    payload_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # raw telemetry bytes
    # "<org or platform>:<caller key or random>" -> enqueue with the same key is a no-op returning the first job
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
