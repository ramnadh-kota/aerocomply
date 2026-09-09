"""AOG events and blockers (Milestone 3.9)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aog_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "aircraft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aircraft.id"),
            nullable=False,
        ),
        sa.Column(
            "work_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("work_orders.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DECLARED"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="CRITICAL"),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column(
            "declared_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("recovery_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_aog_events_organization_id", "aog_events", ["organization_id"])
    op.create_index("ix_aog_events_aircraft_id", "aog_events", ["aircraft_id"])
    op.create_index("ix_aog_events_work_order_id", "aog_events", ["work_order_id"])
    op.create_index("ix_aog_events_status", "aog_events", ["status"])

    op.create_table(
        "aog_blockers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "aog_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aog_events.id"),
            nullable=False,
        ),
        sa.Column("blocker_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_aog_blockers_organization_id", "aog_blockers", ["organization_id"])
    op.create_index("ix_aog_blockers_aog_event_id", "aog_blockers", ["aog_event_id"])


def downgrade() -> None:
    op.drop_index("ix_aog_blockers_aog_event_id", table_name="aog_blockers")
    op.drop_index("ix_aog_blockers_organization_id", table_name="aog_blockers")
    op.drop_table("aog_blockers")

    op.drop_index("ix_aog_events_status", table_name="aog_events")
    op.drop_index("ix_aog_events_work_order_id", table_name="aog_events")
    op.drop_index("ix_aog_events_aircraft_id", table_name="aog_events")
    op.drop_index("ix_aog_events_organization_id", table_name="aog_events")
    op.drop_table("aog_events")
