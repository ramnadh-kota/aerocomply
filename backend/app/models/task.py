import datetime
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class TaskExecutionState:
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


ALL_TASK_EXECUTION_STATES = {
    TaskExecutionState.PENDING,
    TaskExecutionState.IN_PROGRESS,
    TaskExecutionState.COMPLETED,
    TaskExecutionState.CANCELLED,
}


class Task(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_execution_state", "execution_state"),
    )

    work_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=False, index=True
    )
    task_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    execution_state: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TaskExecutionState.PENDING
    )
    assigned_technician_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    # M17.6A: requirement-level flag saying evidence must exist and be
    # ACCEPTED for this task before release readiness can pass. Deliberately
    # placed here rather than as a boolean on Evidence itself, since Evidence
    # rows are created per-submission (and may not exist yet at all) while
    # Task is the actual requirement/unit-of-work being asked for evidence.
    # Defaults to False so every pre-existing task (and its readiness
    # evaluation) is completely unaffected.
    evidence_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

