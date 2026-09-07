"""Add rejection_reason to inspection_requirements

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inspection_requirements", sa.Column("rejection_reason", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("inspection_requirements", "rejection_reason")
