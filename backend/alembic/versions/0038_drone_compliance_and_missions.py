"""M1.5: Drone compliance asset support, Mission domain, and flight mission link.

1. `compliance_assessments.aircraft_id` made nullable so compliance assessments
   can evaluate standalone drone / non-aircraft Assets directly (via asset_id)
   while preserving full backward compatibility for existing aircraft assessments.
2. `missions` table created for operational mission planning, dispatch, and internal
   authorization within the platform.
3. `flights.mission_id` added as nullable FK -> `missions.id` for end-to-end
   flight-to-mission traceability.

Revision ID: 0038
Revises: 0037
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Make compliance_assessments.aircraft_id nullable
    op.alter_column(
        "compliance_assessments",
        "aircraft_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # 2. Create missions table
    op.create_table(
        "missions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pilot_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PLANNED"),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("operating_area", sa.String(length=255), nullable=True),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authorized_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["pilot_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_missions_organization_id", "missions", ["organization_id"])
    op.create_index("ix_missions_asset_id", "missions", ["asset_id"])
    op.create_index("ix_missions_pilot_user_id", "missions", ["pilot_user_id"])
    op.create_index("ix_missions_status", "missions", ["status"])

    # 3. Add mission_id to flights table
    op.add_column(
        "flights",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_flights_mission_id", "flights", ["mission_id"])
    op.create_foreign_key(
        "fk_flights_mission_id_missions",
        "flights",
        "missions",
        ["mission_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_flights_mission_id_missions", "flights", type_="foreignkey")
    op.drop_index("ix_flights_mission_id", table_name="flights")
    op.drop_column("flights", "mission_id")

    op.drop_index("ix_missions_status", table_name="missions")
    op.drop_index("ix_missions_pilot_user_id", table_name="missions")
    op.drop_index("ix_missions_asset_id", table_name="missions")
    op.drop_index("ix_missions_organization_id", table_name="missions")
    op.drop_table("missions")

    op.alter_column(
        "compliance_assessments",
        "aircraft_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
