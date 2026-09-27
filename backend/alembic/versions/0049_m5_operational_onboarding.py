"""M5: Operational Flight Records, Historical Baselines, and Customer Data Onboarding.

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-27

Changes:
- Creates asset_historical_baselines table for carry-in hours/cycles accounting.
- Creates tenant_import_mappings table for persisted organization column mappings.
- Extends flights table with operational flight attributes:
  - flight_number, origin, destination, departure_time, arrival_time,
  - mission_type, status, source, source_row_id.
- Extends import_jobs table with multi-format, sheet selection, and validation fields:
  - file_hash, sheet_names, selected_sheet, column_mapping, match_strategy,
  - warning_count, error_count, completed_at.
- Supporting indexes for query and deduplication performance.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create asset_historical_baselines table
    op.create_table(
        "asset_historical_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flight_hours", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("flight_cycles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="MANUAL"),
        sa.Column("evidence_reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_asset_historical_baselines_organization_id", "asset_historical_baselines", ["organization_id"])
    op.create_index("ix_asset_historical_baselines_asset_id", "asset_historical_baselines", ["asset_id"])
    op.create_index("ix_asset_historical_baselines_effective_at", "asset_historical_baselines", ["effective_at"])

    # 2. Create tenant_import_mappings table
    op.create_table(
        "tenant_import_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_tenant_import_mappings_organization_id", "tenant_import_mappings", ["organization_id"])
    op.create_index("ix_tenant_import_mappings_domain", "tenant_import_mappings", ["domain"])

    # 3. Extend flights table
    op.add_column("flights", sa.Column("flight_number", sa.String(length=64), nullable=True))
    op.add_column("flights", sa.Column("origin", sa.String(length=64), nullable=True))
    op.add_column("flights", sa.Column("destination", sa.String(length=64), nullable=True))
    op.add_column("flights", sa.Column("departure_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("flights", sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=True))
    op.add_column("flights", sa.Column("mission_type", sa.String(length=64), nullable=True))
    op.add_column("flights", sa.Column("status", sa.String(length=32), nullable=False, server_default="COMPLETED"))
    op.add_column("flights", sa.Column("source", sa.String(length=32), nullable=False, server_default="MANUAL"))
    op.add_column("flights", sa.Column("source_row_id", sa.String(length=255), nullable=True))

    op.create_index("ix_flights_flight_number", "flights", ["flight_number"])
    op.create_index("ix_flights_status", "flights", ["status"])
    op.create_index("ix_flights_source_row_id", "flights", ["source_row_id"])

    # 4. Extend import_jobs table
    op.add_column("import_jobs", sa.Column("file_hash", sa.String(length=64), nullable=True))
    op.add_column("import_jobs", sa.Column("sheet_names", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("import_jobs", sa.Column("selected_sheet", sa.String(length=255), nullable=True))
    op.add_column("import_jobs", sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("import_jobs", sa.Column("match_strategy", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("import_jobs", sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("import_jobs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_import_jobs_file_hash", "import_jobs", ["file_hash"])


def downgrade() -> None:
    # 4. Downgrade import_jobs
    op.drop_index("ix_import_jobs_file_hash", table_name="import_jobs")
    op.drop_column("import_jobs", "completed_at")
    op.drop_column("import_jobs", "error_count")
    op.drop_column("import_jobs", "warning_count")
    op.drop_column("import_jobs", "match_strategy")
    op.drop_column("import_jobs", "column_mapping")
    op.drop_column("import_jobs", "selected_sheet")
    op.drop_column("import_jobs", "sheet_names")
    op.drop_column("import_jobs", "file_hash")

    # 3. Downgrade flights
    op.drop_index("ix_flights_source_row_id", table_name="flights")
    op.drop_index("ix_flights_status", table_name="flights")
    op.drop_index("ix_flights_flight_number", table_name="flights")
    op.drop_column("flights", "source_row_id")
    op.drop_column("flights", "source")
    op.drop_column("flights", "status")
    op.drop_column("flights", "mission_type")
    op.drop_column("flights", "arrival_time")
    op.drop_column("flights", "departure_time")
    op.drop_column("flights", "destination")
    op.drop_column("flights", "origin")
    op.drop_column("flights", "flight_number")

    # 2. Downgrade tenant_import_mappings
    op.drop_index("ix_tenant_import_mappings_domain", table_name="tenant_import_mappings")
    op.drop_index("ix_tenant_import_mappings_organization_id", table_name="tenant_import_mappings")
    op.drop_table("tenant_import_mappings")

    # 1. Downgrade asset_historical_baselines
    op.drop_index("ix_asset_historical_baselines_effective_at", table_name="asset_historical_baselines")
    op.drop_index("ix_asset_historical_baselines_asset_id", table_name="asset_historical_baselines")
    op.drop_index("ix_asset_historical_baselines_organization_id", table_name="asset_historical_baselines")
    op.drop_table("asset_historical_baselines")
