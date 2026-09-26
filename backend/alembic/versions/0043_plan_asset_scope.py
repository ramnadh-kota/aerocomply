"""M21.6: add Plan.asset_scope for commercial asset vertical domain.

Adds a nullable string(32) column `plans.asset_scope` to categorize plans by
aerospace asset scope (DRONE, AIRCRAFT, HELICOPTER, EVTOL, or NULL for universal/
unassigned). Completely additive and non-breaking; existing plans default to NULL.

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("asset_scope", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_plans_asset_scope", "plans", ["asset_scope"])


def downgrade() -> None:
    op.drop_index("ix_plans_asset_scope", table_name="plans")
    op.drop_column("plans", "asset_scope")
