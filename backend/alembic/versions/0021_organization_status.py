"""Organization platform-managed status (ACTIVE/SUSPENDED)

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "status")
