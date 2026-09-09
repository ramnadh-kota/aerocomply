"""Parts and vendors persistence (Milestone 3 foundation)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid_pk = dict(server_default=sa.text("gen_random_uuid()"), primary_key=True)

    op.create_table(
        "parts",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("part_number", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("manufacturer", sa.String(length=255), nullable=True),
        sa.Column("condition", sa.String(length=32), nullable=True),
        sa.Column(
            "quantity_on_hand", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "quantity_reserved", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_parts_organization_id", "parts", ["organization_id"])
    op.create_index("ix_parts_part_number", "parts", ["part_number"])

    op.create_table(
        "vendors",
        sa.Column("id", postgresql.UUID(as_uuid=True), **uuid_pk),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("certifications", sa.Text(), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_vendors_organization_id", "vendors", ["organization_id"])
    op.create_index("ix_vendors_name", "vendors", ["name"])


def downgrade() -> None:
    op.drop_index("ix_vendors_name", table_name="vendors")
    op.drop_index("ix_vendors_organization_id", table_name="vendors")
    op.drop_table("vendors")

    op.drop_index("ix_parts_part_number", table_name="parts")
    op.drop_index("ix_parts_organization_id", table_name="parts")
    op.drop_table("parts")
