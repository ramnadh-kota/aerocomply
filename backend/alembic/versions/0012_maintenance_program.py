"""Maintenance program: requirements, applicability, accomplishments (Milestone 3.10)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_requirements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("ata_chapter", sa.String(length=16), nullable=False),
        sa.Column("interval_type", sa.String(length=16), nullable=False),
        sa.Column("fh_interval", sa.Integer(), nullable=True),
        sa.Column("fc_interval", sa.Integer(), nullable=True),
        sa.Column("calendar_interval_days", sa.Integer(), nullable=True),
        sa.Column("task_reference", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_maintenance_requirements_organization_id",
        "maintenance_requirements",
        ["organization_id"],
    )

    op.create_table(
        "maintenance_requirement_applicabilities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requirement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_requirements.id"),
            nullable=False,
        ),
        sa.Column(
            "aircraft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aircraft.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "requirement_id", "aircraft_id", name="uq_maintenance_requirement_applicability"
        ),
    )
    op.create_index(
        "ix_maintenance_requirement_applicabilities_organization_id",
        "maintenance_requirement_applicabilities",
        ["organization_id"],
    )
    op.create_index(
        "ix_maintenance_requirement_applicabilities_requirement_id",
        "maintenance_requirement_applicabilities",
        ["requirement_id"],
    )
    op.create_index(
        "ix_maintenance_requirement_applicabilities_aircraft_id",
        "maintenance_requirement_applicabilities",
        ["aircraft_id"],
    )

    op.create_table(
        "maintenance_accomplishments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requirement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_requirements.id"),
            nullable=False,
        ),
        sa.Column(
            "aircraft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aircraft.id"),
            nullable=False,
        ),
        sa.Column("accomplished_at", sa.Date(), nullable=False),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_orders.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_maintenance_accomplishments_organization_id",
        "maintenance_accomplishments",
        ["organization_id"],
    )
    op.create_index(
        "ix_maintenance_accomplishments_requirement_id",
        "maintenance_accomplishments",
        ["requirement_id"],
    )
    op.create_index(
        "ix_maintenance_accomplishments_aircraft_id",
        "maintenance_accomplishments",
        ["aircraft_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_maintenance_accomplishments_aircraft_id", table_name="maintenance_accomplishments"
    )
    op.drop_index(
        "ix_maintenance_accomplishments_requirement_id",
        table_name="maintenance_accomplishments",
    )
    op.drop_index(
        "ix_maintenance_accomplishments_organization_id",
        table_name="maintenance_accomplishments",
    )
    op.drop_table("maintenance_accomplishments")

    op.drop_index(
        "ix_maintenance_requirement_applicabilities_aircraft_id",
        table_name="maintenance_requirement_applicabilities",
    )
    op.drop_index(
        "ix_maintenance_requirement_applicabilities_requirement_id",
        table_name="maintenance_requirement_applicabilities",
    )
    op.drop_index(
        "ix_maintenance_requirement_applicabilities_organization_id",
        table_name="maintenance_requirement_applicabilities",
    )
    op.drop_table("maintenance_requirement_applicabilities")

    op.drop_index(
        "ix_maintenance_requirements_organization_id", table_name="maintenance_requirements"
    )
    op.drop_table("maintenance_requirements")
