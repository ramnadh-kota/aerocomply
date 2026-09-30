"""0068: helicopter and eVTOL/AAM detail tables (1:1 with assets).

Revises: 0067
Additive only. Downgrade drops both tables (detail rows only; the assets themselves are untouched).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0068"
down_revision: str | None = "0067"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "helicopter_details",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rotor_system", sa.String(32), nullable=False),
        sa.Column("main_rotor_blade_count", sa.Integer(), nullable=True),
        sa.Column("engine_count", sa.Integer(), nullable=True),
        sa.Column("max_takeoff_weight_kg", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("asset_id"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.CheckConstraint("engine_count IS NULL OR engine_count BETWEEN 1 AND 4", name="ck_helicopter_engine_count"),
        sa.CheckConstraint("main_rotor_blade_count IS NULL OR main_rotor_blade_count BETWEEN 2 AND 12",
                           name="ck_helicopter_blade_count"),
        sa.CheckConstraint("max_takeoff_weight_kg IS NULL OR max_takeoff_weight_kg > 0", name="ck_helicopter_mtow"),
    )
    op.create_table(
        "evtol_details",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("configuration", sa.String(32), nullable=False),
        sa.Column("propulsor_count", sa.Integer(), nullable=True),
        sa.Column("battery_nominal_energy_kwh", sa.Float(), nullable=True),
        sa.Column("hv_bus_nominal_voltage_v", sa.Float(), nullable=True),
        sa.Column("max_takeoff_weight_kg", sa.Float(), nullable=True),
        sa.Column("passenger_capacity", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("asset_id"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.CheckConstraint("propulsor_count IS NULL OR propulsor_count BETWEEN 1 AND 64", name="ck_evtol_propulsors"),
        sa.CheckConstraint("battery_nominal_energy_kwh IS NULL OR battery_nominal_energy_kwh > 0", name="ck_evtol_energy"),
        sa.CheckConstraint("hv_bus_nominal_voltage_v IS NULL OR hv_bus_nominal_voltage_v > 0", name="ck_evtol_hv_bus"),
        sa.CheckConstraint("max_takeoff_weight_kg IS NULL OR max_takeoff_weight_kg > 0", name="ck_evtol_mtow"),
        sa.CheckConstraint("passenger_capacity IS NULL OR passenger_capacity >= 0", name="ck_evtol_pax"),
    )


def downgrade() -> None:
    op.drop_table("evtol_details")
    op.drop_table("helicopter_details")
