"""M21.7: create plan_limits table for commercial plan-level usage limits.

Adds generic PlanLimit model to store commercial baseline usage ceilings
(max_assets, max_users, monthly_work_orders, storage_gb, etc.) attached to
Plans. Subscribed tenants inherit these limits as defaults, which can be
further customized via TenantUsageLimit overrides.

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_limits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("limit_key", sa.String(128), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("is_unlimited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_plan_limits_plan_id_plans",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "plan_id",
            "limit_key",
            name="uq_plan_limits_plan_id_limit_key",
        ),
    )
    op.create_index("ix_plan_limits_plan_id", "plan_limits", ["plan_id"])
    op.create_index("ix_plan_limits_limit_key", "plan_limits", ["limit_key"])


def downgrade() -> None:
    op.drop_index("ix_plan_limits_limit_key", table_name="plan_limits")
    op.drop_index("ix_plan_limits_plan_id", table_name="plan_limits")
    op.drop_table("plan_limits")
