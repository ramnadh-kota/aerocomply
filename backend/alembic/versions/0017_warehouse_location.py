"""Warehouse / Location domain + Part.location_id (M3 inventory depth)

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "code", name="uq_warehouse_org_code"),
    )
    op.create_index("ix_warehouses_organization_id", "warehouses", ["organization_id"])
    op.create_index("ix_warehouses_code", "warehouses", ["code"])

    op.create_table(
        "locations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "warehouse_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("warehouses.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_location_warehouse_code"),
    )
    op.create_index("ix_locations_organization_id", "locations", ["organization_id"])
    op.create_index("ix_locations_warehouse_id", "locations", ["warehouse_id"])

    op.add_column(
        "parts",
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_parts_location_id", "parts", ["location_id"])


def downgrade() -> None:
    op.drop_index("ix_parts_location_id", table_name="parts")
    op.drop_column("parts", "location_id")

    op.drop_index("ix_locations_warehouse_id", table_name="locations")
    op.drop_index("ix_locations_organization_id", table_name="locations")
    op.drop_table("locations")

    op.drop_index("ix_warehouses_code", table_name="warehouses")
    op.drop_index("ix_warehouses_organization_id", table_name="warehouses")
    op.drop_table("warehouses")
