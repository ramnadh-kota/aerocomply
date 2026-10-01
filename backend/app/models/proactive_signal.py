import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, event
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class ProactiveSignalRecord(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """M7: Persistent record of proactive aerospace intelligence signals and their lifecycle.

    Stores deterministic signals (maintenance threshold, inspection due, recurring findings,
    evidence gaps, compliance risks, utilization spikes) and tracks operator lifecycle state
    (OPEN, ACKNOWLEDGED, IN_REVIEW, RESOLVED, DISMISSED) with full audit provenance.
    """

    __tablename__ = "proactive_signal_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "signal_key", name="uq_proactive_signal_org_key"),
        Index("ix_proactive_signal_org_status", "organization_id", "status"),
        Index("ix_proactive_signal_org_asset", "organization_id", "asset_id"),
        Index("ix_proactive_signal_org_type", "organization_id", "signal_type"),
    )

    signal_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("components.id", ondelete="SET NULL"), nullable=True, index=True
    )

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    contributing_factors_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recommended_actions_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    # Operator Lifecycle attribution
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["ProactiveSignalRecord"]


@event.listens_for(ProactiveSignalRecord, "after_insert")
def _count_created_signal(mapper, connection, target) -> None:  # noqa: ANN001 - SQLAlchemy event signature
    """Every M7 signal creation path (HUMS exceedance/health/diagnostic/prognostic and the proactive sync) is counted here."""
    from app.core import metrics

    metrics.M7_SIGNALS.inc(event="created", signal_type=str(target.signal_type))
