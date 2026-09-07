"""MRO domain slice: aircraft, work_orders, tasks, evidence, inspection_requirements

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_pk = dict(server_default=sa.text("gen_random_uuid()"), primary_key=True)

    op.create_table(
        "aircraft",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("registration", sa.String(length=16), nullable=False),
        sa.Column("msn", sa.String(length=64), nullable=False),
        sa.Column("aircraft_type", sa.String(length=128), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'ACTIVE'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_aircraft_organization_id", "aircraft", ["organization_id"])
    op.create_index("ix_aircraft_registration", "aircraft", ["registration"])

    op.create_table(
        "work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aircraft_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_order_number", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'OPEN'")
        ),
        sa.Column(
            "priority", sa.String(length=32), nullable=False, server_default=sa.text("'NORMAL'")
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["aircraft_id"], ["aircraft.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_work_orders_organization_id", "work_orders", ["organization_id"])
    op.create_index("ix_work_orders_aircraft_id", "work_orders", ["aircraft_id"])
    op.create_index("ix_work_orders_work_order_number", "work_orders", ["work_order_number"])

    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "execution_state",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
    )
    op.create_index("ix_tasks_organization_id", "tasks", ["organization_id"])
    op.create_index("ix_tasks_work_order_id", "tasks", ["work_order_id"])

    op.create_table(
        "evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'REQUIRED'")
        ),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"]),
    )
    op.create_index("ix_evidence_organization_id", "evidence", ["organization_id"])
    op.create_index("ix_evidence_task_id", "evidence", ["task_id"])

    op.create_table(
        "inspection_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("inspector_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'PENDING'")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.ForeignKeyConstraint(["inspector_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_inspection_requirements_organization_id", "inspection_requirements", ["organization_id"]
    )
    op.create_index(
        "ix_inspection_requirements_task_id", "inspection_requirements", ["task_id"]
    )
    op.create_index(
        "ix_inspection_requirements_work_order_id", "inspection_requirements", ["work_order_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inspection_requirements_work_order_id", table_name="inspection_requirements"
    )
    op.drop_index("ix_inspection_requirements_task_id", table_name="inspection_requirements")
    op.drop_index(
        "ix_inspection_requirements_organization_id", table_name="inspection_requirements"
    )
    op.drop_table("inspection_requirements")

    op.drop_index("ix_evidence_task_id", table_name="evidence")
    op.drop_index("ix_evidence_organization_id", table_name="evidence")
    op.drop_table("evidence")

    op.drop_index("ix_tasks_work_order_id", table_name="tasks")
    op.drop_index("ix_tasks_organization_id", table_name="tasks")
    op.drop_table("tasks")

    op.drop_index("ix_work_orders_work_order_number", table_name="work_orders")
    op.drop_index("ix_work_orders_aircraft_id", table_name="work_orders")
    op.drop_index("ix_work_orders_organization_id", table_name="work_orders")
    op.drop_table("work_orders")

    op.drop_index("ix_aircraft_registration", table_name="aircraft")
    op.drop_index("ix_aircraft_organization_id", table_name="aircraft")
    op.drop_table("aircraft")
