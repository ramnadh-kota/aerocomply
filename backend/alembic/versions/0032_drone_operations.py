"""Phase 18.6: Drone Operations vertical slice foundation -- batteries,
components, flights.

Written by hand, matching prior migrations' precedent (autogenerate is
currently broken on this codebase).

Architecture decision (see app/models/battery.py, component.py, flight.py
docstrings for the full writeup): Drone is NOT a new asset identity --
it is Asset with asset_type=DRONE (already anticipated by
app.models.asset.AssetType since Phase 1A), using Asset's own
manufacturer/model/serial_number/registration/status/facility_id fields
directly. No DroneDetail table is added in this migration: every field
genuinely needed for the drone vertical slice already exists on Asset;
one can be added later the same way AircraftDetail was, without breaking
this API, if a real drone-specific field emerges.

Battery and Component are new, dedicated tables (not a reuse of the
existing Part model): Part is quantity-based inventory stock (on_hand/
reserved/quarantined counters, no per-unit "currently installed on this
asset" or health/cycle tracking) -- a fundamentally different shape from
"this one serialized battery, right now, on this one drone, with N charge
cycles and a health percentage." Reusing Part would require bolting
asset-installation and health semantics onto an inventory-counting model
that was never designed for either. Each references its current asset via
a single nullable asset_id FK (never a competing field on Asset pointing
back) -- one direction, one source of truth, matching the milestone's
explicit anti-pattern warning.

Flight is asset-native from creation (NOT NULL asset_id, no aircraft_id
compatibility concept -- flights are a new domain, not a migrated one).

Also loosens `aircraft_id` to nullable on exactly three existing tables --
work_orders, maintenance_requirement_applicabilities, and
maintenance_accomplishments -- the minimum
required for a Drone (an Asset with no Aircraft row) to ever get a row in
either, which is what this milestone's deployment-readiness maintenance
and failed-inspection checks need. This was correctly deferred out of
Phase 1B (0031's own docstring) until a real, concrete need proved it was
necessary; it is now proven necessary by this migration's own tests.
Loosening a NOT NULL constraint is always backward-compatible -- every
existing aircraft-linked row keeps its aircraft_id unchanged, and no
existing service/API behavior changes (they still always supply
aircraft_id for aircraft-based records).

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "batteries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("serial_number", sa.String(128), nullable=False),
        sa.Column("manufacturer", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("capacity_mah", sa.Integer(), nullable=True),
        sa.Column("voltage", sa.Integer(), nullable=True),
        sa.Column("cycle_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("health_percent", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="GOOD"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_batteries_asset_id_assets", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_batteries_organization_id", "batteries", ["organization_id"])
    op.create_index("ix_batteries_asset_id", "batteries", ["asset_id"])

    op.create_table(
        "components",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("component_type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("serial_number", sa.String(128), nullable=True),
        sa.Column("manufacturer", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="INSTALLED"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_components_asset_id_assets", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_components_organization_id", "components", ["organization_id"])
    op.create_index("ix_components_asset_id", "components", ["asset_id"])

    op.create_table(
        "flights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flown_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("cycles", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pilot_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_flights_asset_id_assets", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pilot_user_id"],
            ["users.id"],
            name="fk_flights_pilot_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_flights_organization_id", "flights", ["organization_id"])
    op.create_index("ix_flights_asset_id", "flights", ["asset_id"])

    op.alter_column("work_orders", "aircraft_id", nullable=True)
    op.alter_column("maintenance_requirement_applicabilities", "aircraft_id", nullable=True)
    op.alter_column("maintenance_accomplishments", "aircraft_id", nullable=True)


def downgrade() -> None:
    # Restoring NOT NULL is only safe if no drone-only (aircraft_id IS NULL)
    # row was created in the meantime; this migration's own tests never
    # leave such a row committed outside their own transaction, and a
    # downgrade of a live database with real drone-only rows should not
    # happen silently -- so this intentionally lets the ALTER fail loudly
    # (raising) rather than deleting data to force it through.
    op.alter_column("maintenance_accomplishments", "aircraft_id", nullable=False)
    op.alter_column("maintenance_requirement_applicabilities", "aircraft_id", nullable=False)
    op.alter_column("work_orders", "aircraft_id", nullable=False)
    op.drop_index("ix_flights_asset_id", table_name="flights")
    op.drop_index("ix_flights_organization_id", table_name="flights")
    op.drop_table("flights")

    op.drop_index("ix_components_asset_id", table_name="components")
    op.drop_index("ix_components_organization_id", table_name="components")
    op.drop_table("components")

    op.drop_index("ix_batteries_asset_id", table_name="batteries")
    op.drop_index("ix_batteries_organization_id", table_name="batteries")
    op.drop_table("batteries")
