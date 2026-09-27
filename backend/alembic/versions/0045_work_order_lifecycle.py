"""0045: Work Order Lifecycle and Task Enhancements.

Adds missing operational fields to WorkOrder and Task models:
- WorkOrder: title, description, work_order_type, maintenance_category,
  scheduled_start, scheduled_end, actual_start, actual_end, due_at,
  estimated_hours, actual_hours, estimated_cost, actual_cost,
  assigned_to_user_id, location, source_type, source_reference,
  compliance_required, compliance_reference, completed_at, closed_at,
  cancelled_at, cancellation_reason.
- Task: task_number, title, estimated_hours, actual_hours, started_at,
  completed_at, sequence, notes.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Enhance work_orders table
    op.add_column(
        "work_orders",
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            server_default="Untitled Work Order",
        ),
    )
    op.add_column("work_orders", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "work_orders",
        sa.Column(
            "work_order_type",
            sa.String(64),
            nullable=False,
            server_default="CORRECTIVE",
        ),
    )
    op.add_column("work_orders", sa.Column("maintenance_category", sa.String(64), nullable=True))
    op.add_column("work_orders", sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("estimated_hours", sa.Float(), nullable=True))
    op.add_column("work_orders", sa.Column("actual_hours", sa.Float(), nullable=True))
    op.add_column("work_orders", sa.Column("estimated_cost", sa.Float(), nullable=True))
    op.add_column("work_orders", sa.Column("actual_cost", sa.Float(), nullable=True))
    op.add_column(
        "work_orders",
        sa.Column(
            "assigned_to_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("work_orders", sa.Column("location", sa.String(128), nullable=True))
    op.add_column("work_orders", sa.Column("source_type", sa.String(64), nullable=True))
    op.add_column("work_orders", sa.Column("source_reference", sa.String(255), nullable=True))
    op.add_column(
        "work_orders",
        sa.Column(
            "compliance_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("work_orders", sa.Column("compliance_reference", sa.String(255), nullable=True))
    op.add_column("work_orders", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("work_orders", sa.Column("cancellation_reason", sa.Text(), nullable=True))

    op.create_index("ix_work_orders_due_at", "work_orders", ["due_at"])
    op.create_index("ix_work_orders_assigned_to_user_id", "work_orders", ["assigned_to_user_id"])
    op.create_index("ix_work_orders_status", "work_orders", ["status"])
    op.create_index("ix_work_orders_priority", "work_orders", ["priority"])
    op.create_index("ix_work_orders_work_order_type", "work_orders", ["work_order_type"])

    # 2. Enhance tasks table
    op.add_column("tasks", sa.Column("task_number", sa.String(32), nullable=True))
    op.add_column("tasks", sa.Column("title", sa.String(255), nullable=True))
    op.add_column("tasks", sa.Column("estimated_hours", sa.Float(), nullable=True))
    op.add_column("tasks", sa.Column("actual_hours", sa.Float(), nullable=True))
    op.add_column("tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "sequence",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column("tasks", sa.Column("notes", sa.Text(), nullable=True))
    op.create_index("ix_tasks_execution_state", "tasks", ["execution_state"])


def downgrade() -> None:
    # Downgrade tasks
    op.drop_index("ix_tasks_execution_state", table_name="tasks")
    op.drop_column("tasks", "notes")
    op.drop_column("tasks", "sequence")
    op.drop_column("tasks", "completed_at")
    op.drop_column("tasks", "started_at")
    op.drop_column("tasks", "actual_hours")
    op.drop_column("tasks", "estimated_hours")
    op.drop_column("tasks", "title")
    op.drop_column("tasks", "task_number")

    # Downgrade work_orders
    op.drop_index("ix_work_orders_work_order_type", table_name="work_orders")
    op.drop_index("ix_work_orders_priority", table_name="work_orders")
    op.drop_index("ix_work_orders_status", table_name="work_orders")
    op.drop_index("ix_work_orders_assigned_to_user_id", table_name="work_orders")
    op.drop_index("ix_work_orders_due_at", table_name="work_orders")

    op.drop_column("work_orders", "cancellation_reason")
    op.drop_column("work_orders", "cancelled_at")
    op.drop_column("work_orders", "closed_at")
    op.drop_column("work_orders", "completed_at")
    op.drop_column("work_orders", "compliance_reference")
    op.drop_column("work_orders", "compliance_required")
    op.drop_column("work_orders", "source_reference")
    op.drop_column("work_orders", "source_type")
    op.drop_column("work_orders", "location")
    op.drop_column("work_orders", "assigned_to_user_id")
    op.drop_column("work_orders", "actual_cost")
    op.drop_column("work_orders", "estimated_cost")
    op.drop_column("work_orders", "actual_hours")
    op.drop_column("work_orders", "estimated_hours")
    op.drop_column("work_orders", "due_at")
    op.drop_column("work_orders", "actual_end")
    op.drop_column("work_orders", "actual_start")
    op.drop_column("work_orders", "scheduled_end")
    op.drop_column("work_orders", "scheduled_start")
    op.drop_column("work_orders", "maintenance_category")
    op.drop_column("work_orders", "work_order_type")
    op.drop_column("work_orders", "description")
    op.drop_column("work_orders", "title")
