"""M17.5A: extend maintenance applicability/accomplishment to serialized
Battery and Component -- the same nullable-FK-per-object-type pattern
already used for aircraft_id (original) and asset_id (migration 0031/0032,
Drone compatibility), extended one step further for life-limited installed
items. No new tables: MaintenanceRequirementApplicability and
MaintenanceAccomplishment already express "this requirement applies to
that object" / "this object had this requirement performed" -- a
Battery/Component is just another object type, not a different concept,
so this migration only adds two more nullable FK columns to each existing
table rather than creating a parallel maintenance architecture.

Exactly one of aircraft_id / asset_id / battery_id / component_id is
expected to be set per row (enforced at the service layer, same as the
existing aircraft_id/asset_id pair -- no CHECK constraint is added here,
consistent with this codebase's precedent of not adding a DB-level
mutual-exclusivity constraint across the two existing nullable FKs
either).

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "maintenance_requirement_applicabilities",
        sa.Column("battery_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "maintenance_requirement_applicabilities",
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_mra_battery_id_batteries",
        "maintenance_requirement_applicabilities",
        "batteries",
        ["battery_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_mra_component_id_components",
        "maintenance_requirement_applicabilities",
        "components",
        ["component_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_maintenance_requirement_applicabilities_battery_id",
        "maintenance_requirement_applicabilities",
        ["battery_id"],
    )
    op.create_index(
        "ix_maintenance_requirement_applicabilities_component_id",
        "maintenance_requirement_applicabilities",
        ["component_id"],
    )

    op.add_column(
        "maintenance_accomplishments",
        sa.Column("battery_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "maintenance_accomplishments",
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_maintenance_accomplishments_battery_id_batteries",
        "maintenance_accomplishments",
        "batteries",
        ["battery_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_maintenance_accomplishments_component_id_components",
        "maintenance_accomplishments",
        "components",
        ["component_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_maintenance_accomplishments_battery_id", "maintenance_accomplishments", ["battery_id"]
    )
    op.create_index(
        "ix_maintenance_accomplishments_component_id",
        "maintenance_accomplishments",
        ["component_id"],
    )

    # aircraft_id/asset_id were already made nullable in prior migrations
    # (0004 aircraft_id NOT NULL originally, loosened by 0031/0032); no
    # change needed there. This migration only loosens NOTHING further --
    # it purely adds two more optional columns.


def downgrade() -> None:
    op.drop_index(
        "ix_maintenance_accomplishments_component_id", table_name="maintenance_accomplishments"
    )
    op.drop_index(
        "ix_maintenance_accomplishments_battery_id", table_name="maintenance_accomplishments"
    )
    op.drop_constraint(
        "fk_maintenance_accomplishments_component_id_components",
        "maintenance_accomplishments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_maintenance_accomplishments_battery_id_batteries",
        "maintenance_accomplishments",
        type_="foreignkey",
    )
    op.drop_column("maintenance_accomplishments", "component_id")
    op.drop_column("maintenance_accomplishments", "battery_id")

    op.drop_index(
        "ix_maintenance_requirement_applicabilities_component_id",
        table_name="maintenance_requirement_applicabilities",
    )
    op.drop_index(
        "ix_maintenance_requirement_applicabilities_battery_id",
        table_name="maintenance_requirement_applicabilities",
    )
    op.drop_constraint(
        "fk_mra_component_id_components",
        "maintenance_requirement_applicabilities",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_mra_battery_id_batteries",
        "maintenance_requirement_applicabilities",
        type_="foreignkey",
    )
    op.drop_column("maintenance_requirement_applicabilities", "component_id")
    op.drop_column("maintenance_requirement_applicabilities", "battery_id")
