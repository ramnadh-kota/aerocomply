"""M17.2A: Serialized Battery & Component installation history.

Adds two new, additive history tables -- battery_installations and
component_installations -- one row per install-to-removal span. This is
purely additive alongside the existing Battery.asset_id / Component.asset_id
columns (see those models' docstrings): those columns remain the single
source of truth for "where is this thing installed right now"; these new
tables answer "where has it been, and when." Neither existing column is
touched by this migration.

A generalized single "InstallationHistory" table (polymorphic across
Battery/Component) was considered and rejected: it would need a nullable
battery_id/component_id pair or a discriminator + generic target_id, both
weaker at the database level than two dedicated FK columns, and this
codebase's own precedent (Battery vs. Component as separate tables rather
than a generic serialized-item table, per 0032's docstring) favors the
concrete, FK-enforced shape here.

Each table enforces "no two simultaneous active installations for the same
battery/component" at the database level via a partial unique index on the
owning id, WHERE removed_at IS NULL -- Postgres treats every NULL as
distinct under a plain UNIQUE constraint, so a partial index is required
(not a column-list UniqueConstraint) to actually block a second open row.

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "battery_installations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("battery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["battery_id"],
            ["batteries.id"],
            name="fk_battery_installations_battery_id_batteries",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name="fk_battery_installations_asset_id_assets",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_battery_installations_organization_id", "battery_installations", ["organization_id"]
    )
    op.create_index(
        "ix_battery_installations_battery_id", "battery_installations", ["battery_id"]
    )
    op.create_index("ix_battery_installations_asset_id", "battery_installations", ["asset_id"])
    op.create_index(
        "uq_battery_installations_battery_id_open",
        "battery_installations",
        ["battery_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )

    op.create_table(
        "component_installations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["component_id"],
            ["components.id"],
            name="fk_component_installations_component_id_components",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name="fk_component_installations_asset_id_assets",
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_component_installations_organization_id",
        "component_installations",
        ["organization_id"],
    )
    op.create_index(
        "ix_component_installations_component_id", "component_installations", ["component_id"]
    )
    op.create_index(
        "ix_component_installations_asset_id", "component_installations", ["asset_id"]
    )
    op.create_index(
        "uq_component_installations_component_id_open",
        "component_installations",
        ["component_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_component_installations_component_id_open", table_name="component_installations"
    )
    op.drop_index("ix_component_installations_asset_id", table_name="component_installations")
    op.drop_index(
        "ix_component_installations_component_id", table_name="component_installations"
    )
    op.drop_index(
        "ix_component_installations_organization_id", table_name="component_installations"
    )
    op.drop_table("component_installations")

    op.drop_index("uq_battery_installations_battery_id_open", table_name="battery_installations")
    op.drop_index("ix_battery_installations_asset_id", table_name="battery_installations")
    op.drop_index("ix_battery_installations_battery_id", table_name="battery_installations")
    op.drop_index(
        "ix_battery_installations_organization_id", table_name="battery_installations"
    )
    op.drop_table("battery_installations")
