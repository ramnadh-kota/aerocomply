"""H5: HUMS Prognostics / Remaining Useful Life.

Revision ID: 0057
Revises: 0056
Create Date: 2026-09-28

Changes:
- Creates hums_degradation_models: versioned degradation-trajectory fits
  (LINEAR/ROBUST_LINEAR), each pointing at a fixed HUMSBaseline row as its
  stable reference (never the continuously-refreshing "current" baseline).
- Creates hums_prognostic_records: versioned RUL estimates (point + lower/
  upper bound + confidence + quality), each an ESTIMATE, NOT A CERTIFIED
  LIFE LIMIT.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057"
down_revision: str | None = "0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hums_degradation_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_type", sa.String(length=64), nullable=False),
        sa.Column("reference_baseline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("model_type", sa.String(length=32), nullable=False),
        sa.Column("model_version", sa.String(length=16), nullable=False, server_default="h5.1"),
        sa.Column("fit_slope", sa.Float(), nullable=False),
        sa.Column("fit_intercept", sa.Float(), nullable=False),
        sa.Column("fit_error", sa.Float(), nullable=False),
        sa.Column("r_squared", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("usage_unit", sa.String(length=32), nullable=False),
        sa.Column("usage_span", sa.Float(), nullable=False),
        sa.Column("trajectory_state", sa.String(length=32), nullable=False),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sensor_id"], ["hums_sensors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_baseline_id"], ["hums_baselines.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_hums_degmodel_organization_id", "hums_degradation_models", ["organization_id"])
    op.create_index("ix_hums_degmodel_asset_id", "hums_degradation_models", ["asset_id"])
    op.create_index("ix_hums_degmodel_component_id", "hums_degradation_models", ["component_id"])
    op.create_index("ix_hums_degmodel_sensor_id", "hums_degradation_models", ["sensor_id"])
    op.create_index("ix_hums_degmodel_feature_type", "hums_degradation_models", ["feature_type"])
    op.create_index("ix_hums_degmodel_org_sensor_feature_current", "hums_degradation_models", ["organization_id", "sensor_id", "feature_type", "is_current"])

    op.create_table(
        "hums_prognostic_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_type", sa.String(length=64), nullable=False),
        sa.Column("degradation_model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("diagnostic_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=True),
        sa.Column("threshold_type", sa.String(length=32), nullable=True),
        sa.Column("rul_estimate", sa.Float(), nullable=True),
        sa.Column("rul_lower", sa.Float(), nullable=True),
        sa.Column("rul_upper", sa.Float(), nullable=True),
        sa.Column("rul_unit", sa.String(length=32), nullable=True),
        sa.Column("extrapolation_distance", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("quality", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sensor_id"], ["hums_sensors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["degradation_model_id"], ["hums_degradation_models.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["diagnostic_candidate_id"], ["hums_diagnostic_candidates.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_hums_prognostic_organization_id", "hums_prognostic_records", ["organization_id"])
    op.create_index("ix_hums_prognostic_asset_id", "hums_prognostic_records", ["asset_id"])
    op.create_index("ix_hums_prognostic_component_id", "hums_prognostic_records", ["component_id"])
    op.create_index("ix_hums_prognostic_sensor_id", "hums_prognostic_records", ["sensor_id"])
    op.create_index("ix_hums_prognostic_org_sensor_feature_current", "hums_prognostic_records", ["organization_id", "sensor_id", "feature_type", "is_current"])
    op.create_index("ix_hums_prognostic_org_asset", "hums_prognostic_records", ["organization_id", "asset_id"])


def downgrade() -> None:
    op.drop_table("hums_prognostic_records")
    op.drop_table("hums_degradation_models")
