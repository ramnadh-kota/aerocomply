"""Procurement requests (Milestone 3.6)

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "procurement_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "aircraft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aircraft.id"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_orders.id"),
            nullable=True,
        ),
        sa.Column(
            "task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id"), nullable=True
        ),
        sa.Column(
            "part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id"), nullable=True
        ),
        sa.Column("part_number", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="ROUTINE"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "requested_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "preferred_vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id"),
            nullable=True,
        ),
        sa.Column(
            "selected_vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("estimated_cost_cents", sa.Integer(), nullable=True),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("clarification_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_procurement_requests_quantity_positive"),
    )
    op.create_index(
        "ix_procurement_requests_organization_id", "procurement_requests", ["organization_id"]
    )
    op.create_index(
        "ix_procurement_requests_aircraft_id", "procurement_requests", ["aircraft_id"]
    )
    op.create_index(
        "ix_procurement_requests_work_order_id", "procurement_requests", ["work_order_id"]
    )
    op.create_index("ix_procurement_requests_status", "procurement_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_procurement_requests_status", table_name="procurement_requests")
    op.drop_index("ix_procurement_requests_work_order_id", table_name="procurement_requests")
    op.drop_index("ix_procurement_requests_aircraft_id", table_name="procurement_requests")
    op.drop_index("ix_procurement_requests_organization_id", table_name="procurement_requests")
    op.drop_table("procurement_requests")
