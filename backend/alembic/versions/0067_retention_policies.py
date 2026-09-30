"""0067: data retention policies (all disabled by default).

Revises: 0066
Additive only: one table. Downgrade drops it (policies only; no customer data is touched).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0067"
down_revision: str | None = "0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_key", sa.String(64), nullable=False),
        sa.Column("data_class", sa.String(32), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("scope_key", "data_class", name="uq_retention_scope_class"),
        sa.CheckConstraint("retention_days >= 1", name="ck_retention_days_positive"),
    )
    op.create_index("ix_retention_policies_organization_id", "retention_policies", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_retention_policies_organization_id", table_name="retention_policies")
    op.drop_table("retention_policies")
