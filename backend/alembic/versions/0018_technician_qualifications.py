"""Technician qualifications + Task.assigned_technician_user_id (AOG M-tech)

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "technician_qualifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("aircraft_type", sa.String(length=128), nullable=False),
        sa.Column("qualification_type", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "granted_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_technician_qualifications_organization_id",
        "technician_qualifications",
        ["organization_id"],
    )
    op.create_index(
        "ix_technician_qualifications_user_id", "technician_qualifications", ["user_id"]
    )
    op.create_index(
        "ix_technician_qualifications_aircraft_type",
        "technician_qualifications",
        ["aircraft_type"],
    )

    op.add_column(
        "tasks",
        sa.Column(
            "assigned_technician_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tasks_assigned_technician_user_id", "tasks", ["assigned_technician_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_assigned_technician_user_id", table_name="tasks")
    op.drop_column("tasks", "assigned_technician_user_id")

    op.drop_index(
        "ix_technician_qualifications_aircraft_type", table_name="technician_qualifications"
    )
    op.drop_index("ix_technician_qualifications_user_id", table_name="technician_qualifications")
    op.drop_index(
        "ix_technician_qualifications_organization_id", table_name="technician_qualifications"
    )
    op.drop_table("technician_qualifications")
