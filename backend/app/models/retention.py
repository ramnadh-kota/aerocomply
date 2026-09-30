"""Data retention policies. Nothing is ever purged unless a policy row exists AND is enabled (default: disabled)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class RetentionClass:
    TELEMETRY_READINGS = "TELEMETRY_READINGS"          # hums_sensor_readings (raw samples)
    TELEMETRY_EVENT_LOG = "TELEMETRY_EVENT_LOG"        # telemetry_event_logs (idempotency / provenance ledger)
    BACKGROUND_JOBS = "BACKGROUND_JOBS"                # finished background_jobs
    HUMS_FEATURES = "HUMS_FEATURES"                    # derived feature rows (the largest table per ingested event)
    ALL = frozenset({TELEMETRY_READINGS, TELEMETRY_EVENT_LOG, BACKGROUND_JOBS, HUMS_FEATURES})


class RetentionPolicy(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "retention_policies"
    __table_args__ = (
        UniqueConstraint("scope_key", "data_class", name="uq_retention_scope_class"),
        CheckConstraint("retention_days >= 1", name="ck_retention_days_positive"),
    )

    # NULL organization_id = platform default, applied to every tenant without its own policy for the class.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope_key: Mapped[str] = mapped_column(String(64), nullable=False)      # organization id, or 'platform'
    data_class: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
