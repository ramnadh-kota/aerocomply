"""H2: HUMS Advanced Signal Processing & Feature Engine.

Revision ID: 0052
Revises: 0051
Create Date: 2026-09-27

Changes:
- Creates hums_features table for persisted, traceable signal-processing
  feature output (time-domain, frequency-domain, domain-specific).
- Adds tenant/asset/sensor/feature_type/timestamp composite indexes for
  feature-history and trend queries.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: str | None = "0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hums_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("measurement_type", sa.String(length=64), nullable=False),
        sa.Column("feature_type", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("quality", sa.String(length=32), nullable=False, server_default="GOOD"),
        sa.Column("calculation_method", sa.String(length=128), nullable=False),
        sa.Column("processor_version", sa.String(length=32), nullable=False, server_default="h2.1"),
        sa.Column("source_reading_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("feature_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["hums_sensors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_hums_features_organization_id", "hums_features", ["organization_id"])
    op.create_index("ix_hums_features_sensor_id", "hums_features", ["sensor_id"])
    op.create_index("ix_hums_features_asset_id", "hums_features", ["asset_id"])
    op.create_index("ix_hums_features_component_id", "hums_features", ["component_id"])
    op.create_index("ix_hums_features_feature_type", "hums_features", ["feature_type"])
    op.create_index("ix_hums_feature_org_sensor_type_ts", "hums_features", ["organization_id", "sensor_id", "feature_type", "window_end"])
    op.create_index("ix_hums_feature_org_asset_type_ts", "hums_features", ["organization_id", "asset_id", "feature_type", "window_end"])


def downgrade() -> None:
    op.drop_table("hums_features")
