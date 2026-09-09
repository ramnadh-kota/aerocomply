import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class PartRequirementStatus:
    """Lifecycle states for a work-order/task part requirement.

    Not a DB enum (plain indexed string, like WorkOrder.status/Task.execution_state
    elsewhere in this codebase) so new states don't require a migration.
    """

    REQUIRED = "REQUIRED"
    SHORT = "SHORT"
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    ORDERED = "ORDERED"
    RECEIVED = "RECEIVED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class PartRequirement(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    """Links a required Part to the Task/WorkOrder that needs it.

    task_id is nullable because a work order can have a part requirement not yet
    broken down into a specific task; work_order_id is always required so the
    requirement is traceable even before task-level granularity exists.
    """

    __tablename__ = "part_requirements"

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=True, index=True
    )
    part_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parts.id"), nullable=False, index=True
    )
    required_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    fulfilled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PartRequirementStatus.REQUIRED
    )
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="NORMAL")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
