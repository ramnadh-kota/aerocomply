"""Telemetry configurable freshness policies.

Revision ID: 0058
Revises: 0057
Create Date: 2026-09-28

Changes:
- Creates telemetry_freshness_policies table for tenant, operational asset, and telemetry source freshness thresholds.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0058"
down_revision: str | None = "0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry_freshness_policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source_system", sa.String(length=64), nullable=True),
        sa.Column("warning_threshold_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("critical_threshold_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "asset_id",
            "source_system",
            name="uq_freshness_policy_org_asset_source",
        ),
    )
    op.create_index("ix_freshness_policy_org_asset", "telemetry_freshness_policies", ["organization_id", "asset_id"])


def downgrade() -> None:
    op.drop_index("ix_freshness_policy_org_asset", table_name="telemetry_freshness_policies")
    op.drop_table("telemetry_freshness_policies")
