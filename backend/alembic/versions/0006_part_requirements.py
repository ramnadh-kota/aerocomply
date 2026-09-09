"""Work order / task part requirement linkage (Milestone 3.3)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "part_requirements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_orders.id"),
            nullable=False,
        ),
        sa.Column(
            "task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=True
        ),
        sa.Column(
            "part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id"), nullable=False
        ),
        sa.Column(
            "required_quantity", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "fulfilled_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default="REQUIRED"
        ),
        sa.Column("priority", sa.String(length=32), nullable=False, server_default="NORMAL"),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint(
            "required_quantity >= 0 AND fulfilled_quantity >= 0",
            name="ck_part_requirements_quantities_non_negative",
        ),
    )
    op.create_index(
        "ix_part_requirements_organization_id", "part_requirements", ["organization_id"]
    )
    op.create_index("ix_part_requirements_work_order_id", "part_requirements", ["work_order_id"])
    op.create_index("ix_part_requirements_task_id", "part_requirements", ["task_id"])
    op.create_index("ix_part_requirements_part_id", "part_requirements", ["part_id"])


def downgrade() -> None:
    op.drop_index("ix_part_requirements_part_id", table_name="part_requirements")
    op.drop_index("ix_part_requirements_task_id", table_name="part_requirements")
    op.drop_index("ix_part_requirements_work_order_id", table_name="part_requirements")
    op.drop_index("ix_part_requirements_organization_id", table_name="part_requirements")
    op.drop_table("part_requirements")
