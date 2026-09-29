"""0062: B1 — DataSource acquisition connector configuration table.

Revises: 0061
Create Date: 2026-09-30

Changes:
1. Create data_sources table: tenant-scoped, persistent connector configurations.
   - Stores connector_type, connection_config (no secrets), secret_reference,
     status, and acquisition health observability counters.
   - Unique constraint: (organization_id, name).
   - Indexes: (organization_id, connector_type), (organization_id, status).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062"
down_revision: str | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("connector_type", sa.String(length=64), nullable=False),
        sa.Column("connection_config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("secret_reference", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("last_acquisition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_events_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_events_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("default_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_data_sources_org_name"),
    )
    op.create_index("ix_data_sources_org_id", "data_sources", ["organization_id"])
    op.create_index(
        "ix_data_sources_org_type", "data_sources", ["organization_id", "connector_type"]
    )
    op.create_index(
        "ix_data_sources_org_status", "data_sources", ["organization_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_data_sources_org_status", table_name="data_sources")
    op.drop_index("ix_data_sources_org_type", table_name="data_sources")
    op.drop_index("ix_data_sources_org_id", table_name="data_sources")
    op.drop_table("data_sources")
