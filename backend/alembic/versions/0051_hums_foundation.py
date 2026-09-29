"""H1: HUMS (Health & Usage Monitoring System) foundation.

Revision ID: 0051
Revises: 0050
Create Date: 2026-09-27

Changes:
- Creates hums_sensors, hums_sensor_readings, hums_exceedances tables.
- Adds tenant/asset/timestamp indexes for high-volume telemetry queries.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051"
down_revision: str | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hums_sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sensor_code", sa.String(length=64), nullable=False),
        sa.Column("sensor_type", sa.String(length=64), nullable=False),
        sa.Column("measurement_type", sa.String(length=64), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("installation_location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="SIMULATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "asset_id", "sensor_code", name="uq_hums_sensor_org_asset_code"),
    )
    op.create_index("ix_hums_sensors_organization_id", "hums_sensors", ["organization_id"])
    op.create_index("ix_hums_sensors_asset_id", "hums_sensors", ["asset_id"])
    op.create_index("ix_hums_sensors_component_id", "hums_sensors", ["component_id"])
    op.create_index("ix_hums_sensor_org_asset", "hums_sensors", ["organization_id", "asset_id"])

    op.create_table(
        "hums_sensor_readings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flight_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("data_quality", sa.String(length=32), nullable=False, server_default="VALID"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="SIMULATED"),
        sa.Column("ingestion_batch", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["hums_sensors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["flight_id"], ["flights.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_hums_sensor_readings_organization_id", "hums_sensor_readings", ["organization_id"])
    op.create_index("ix_hums_sensor_readings_sensor_id", "hums_sensor_readings", ["sensor_id"])
    op.create_index("ix_hums_sensor_readings_asset_id", "hums_sensor_readings", ["asset_id"])
    op.create_index("ix_hums_sensor_readings_flight_id", "hums_sensor_readings", ["flight_id"])
    op.create_index("ix_hums_reading_org_sensor_ts", "hums_sensor_readings", ["organization_id", "sensor_id", "recorded_at"])
    op.create_index("ix_hums_reading_org_asset_ts", "hums_sensor_readings", ["organization_id", "asset_id", "recorded_at"])

    op.create_table(
        "hums_exceedances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sensor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parameter", sa.String(length=64), nullable=False),
        sa.Column("observed_value", sa.Float(), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contributing_reading_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sensor_id"], ["hums_sensors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_hums_exceedances_organization_id", "hums_exceedances", ["organization_id"])
    op.create_index("ix_hums_exceedances_asset_id", "hums_exceedances", ["asset_id"])
    op.create_index("ix_hums_exceedance_org_asset", "hums_exceedances", ["organization_id", "asset_id"])


def downgrade() -> None:
    op.drop_table("hums_exceedances")
    op.drop_table("hums_sensor_readings")
    op.drop_table("hums_sensors")
