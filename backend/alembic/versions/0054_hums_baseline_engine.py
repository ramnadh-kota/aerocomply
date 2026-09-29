"""H3: HUMS Baseline & Health Intelligence.

Revision ID: 0054
Revises: 0053
Create Date: 2026-09-27

Changes:
- Creates hums_baselines table: versioned, per-(sensor, feature_type)
  statistical baselines (mean/std/percentiles/bounds) computed from
  HUMSFeature history. Append-only/versioned (is_current flag), never
  overwritten, so a past health conclusion's baseline lineage stays
  reconstructable.
- Deviation and trend results are deliberately NOT persisted in a new
  table — see docs/HUMS_BASELINE_ENGINE.md for why (derived on demand from
  a bounded HUMSFeature query + the current baseline).
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054"
down_revision: str | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hums_baselines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_type", sa.String(length=64), nullable=False),
        sa.Column("baseline_scope", sa.String(length=16), nullable=False, server_default="ASSET"),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("mean", sa.Float(), nullable=False),
        sa.Column("median", sa.Float(), nullable=False),
        sa.Column("std_dev", sa.Float(), nullable=False),
        sa.Column("minimum", sa.Float(), nullable=False),
        sa.Column("maximum", sa.Float(), nullable=False),
        sa.Column("percentile_05", sa.Float(), nullable=False),
        sa.Column("percentile_25", sa.Float(), nullable=False),
        sa.Column("percentile_50", sa.Float(), nullable=False),
        sa.Column("percentile_75", sa.Float(), nullable=False),
        sa.Column("percentile_95", sa.Float(), nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=False),
        sa.Column("upper_bound", sa.Float(), nullable=False),
        sa.Column("calculation_method", sa.String(length=128), nullable=False),
        sa.Column("source_window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("context_notes", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sensor_id"], ["hums_sensors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_hums_baselines_organization_id", "hums_baselines", ["organization_id"])
    op.create_index("ix_hums_baselines_asset_id", "hums_baselines", ["asset_id"])
    op.create_index("ix_hums_baselines_component_id", "hums_baselines", ["component_id"])
    op.create_index("ix_hums_baselines_sensor_id", "hums_baselines", ["sensor_id"])
    op.create_index("ix_hums_baselines_feature_type", "hums_baselines", ["feature_type"])
    op.create_index("ix_hums_baseline_org_sensor_feature_current", "hums_baselines", ["organization_id", "sensor_id", "feature_type", "is_current"])
    op.create_index("ix_hums_baseline_org_asset_feature", "hums_baselines", ["organization_id", "asset_id", "feature_type"])


def downgrade() -> None:
    op.drop_table("hums_baselines")
