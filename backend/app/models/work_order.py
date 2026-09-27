import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class WorkOrderStatus:
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    PLANNED = "PLANNED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    INSPECTION = "INSPECTION"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


ALL_WORK_ORDER_STATUSES = {
    WorkOrderStatus.DRAFT,
    WorkOrderStatus.OPEN,
    WorkOrderStatus.PLANNED,
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.ON_HOLD,
    WorkOrderStatus.INSPECTION,
    WorkOrderStatus.COMPLETED,
    WorkOrderStatus.CLOSED,
    WorkOrderStatus.CANCELLED,
}


class WorkOrderType:
    CORRECTIVE = "CORRECTIVE"
    PREVENTIVE = "PREVENTIVE"
    SCHEDULED = "SCHEDULED"
    INSPECTION = "INSPECTION"
    COMPONENT_REPLACEMENT = "COMPONENT_REPLACEMENT"
    DEFECT_RECTIFICATION = "DEFECT_RECTIFICATION"
    COMPLIANCE = "COMPLIANCE"
    AOG = "AOG"


ALL_WORK_ORDER_TYPES = {
    WorkOrderType.CORRECTIVE,
    WorkOrderType.PREVENTIVE,
    WorkOrderType.SCHEDULED,
    WorkOrderType.INSPECTION,
    WorkOrderType.COMPONENT_REPLACEMENT,
    WorkOrderType.DEFECT_RECTIFICATION,
    WorkOrderType.COMPLIANCE,
    WorkOrderType.AOG,
}


class WorkOrder(UUIDPKMixin, TenantScopedMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("ix_work_orders_status", "status"),
        Index("ix_work_orders_priority", "priority"),
        Index("ix_work_orders_work_order_type", "work_order_type"),
    )

    # Phase 18.6 (migration 0032): loosened to nullable -- a Drone-based work
    # order has no Aircraft row at all. asset_id (below) is the canonical
    # relationship for those; aircraft_id remains required/populated for
    # every aircraft-based work order exactly as before.
    aircraft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=True, index=True
    )
    # Phase 1B compatibility mapping (migration 0031): the canonical
    # generic-asset identity for this work order, backfilled from
    # Aircraft.asset_id wherever it was already set. Nullable for the same
    # reason Aircraft.asset_id itself is nullable -- see that column's
    # docstring. aircraft_id remains the authoritative relationship;
    # service/router logic is unchanged in this phase (see
    # docs/ARCHITECTURE_ASSET_FOUNDATION.md).
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    work_order_number: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled Work Order")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_order_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default=WorkOrderType.CORRECTIVE
    )
    maintenance_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkOrderStatus.OPEN)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="NORMAL")

    scheduled_start: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scheduled_end: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_start: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_end: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    compliance_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compliance_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

