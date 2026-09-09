"""Deferred items / MEL (Milestone 3.11)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deferred_items",
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
        sa.Column("mel_reference", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.Date(), nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column(
            "deferral_basis", sa.String(length=16), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("operational_limitations", sa.Text(), nullable=True),
        sa.Column("required_actions", sa.Text(), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "approval_status", sa.String(length=16), nullable=False, server_default="NOT_REQUIRED"
        ),
        sa.Column("closed_at", sa.Date(), nullable=True),
        sa.Column("closure_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_deferred_items_organization_id", "deferred_items", ["organization_id"])
    op.create_index("ix_deferred_items_aircraft_id", "deferred_items", ["aircraft_id"])
    op.create_index("ix_deferred_items_status", "deferred_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_deferred_items_status", table_name="deferred_items")
    op.drop_index("ix_deferred_items_aircraft_id", table_name="deferred_items")
    op.drop_index("ix_deferred_items_organization_id", table_name="deferred_items")
    op.drop_table("deferred_items")
