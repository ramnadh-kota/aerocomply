"""Inventory transaction ledger (Milestone 3.4)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id"), nullable=False
        ),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("on_hand_delta", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reserved_delta", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("reference_type", sa.String(length=32), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_inventory_transactions_organization_id",
        "inventory_transactions",
        ["organization_id"],
    )
    op.create_index(
        "ix_inventory_transactions_part_id", "inventory_transactions", ["part_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_transactions_part_id", table_name="inventory_transactions")
    op.drop_index(
        "ix_inventory_transactions_organization_id", table_name="inventory_transactions"
    )
    op.drop_table("inventory_transactions")
