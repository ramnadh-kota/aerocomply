"""Vendor reliability score + vendor/part availability lines (Milestone 3.5)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vendors", sa.Column("reliability_score", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_vendors_reliability_score_range",
        "vendors",
        "reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 100)",
    )

    op.create_table(
        "vendor_part_availabilities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id"),
            nullable=False,
        ),
        sa.Column(
            "part_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("parts.id"), nullable=False
        ),
        sa.Column(
            "availability_status",
            sa.String(length=32),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("quantity_available", sa.Integer(), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("unit_price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("aog_availability", sa.Boolean(), nullable=True),
        sa.Column(
            "certification_status",
            sa.String(length=32),
            nullable=False,
            server_default="UNKNOWN",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("vendor_id", "part_id", name="uq_vendor_part_availability"),
    )
    op.create_index(
        "ix_vendor_part_availabilities_organization_id",
        "vendor_part_availabilities",
        ["organization_id"],
    )
    op.create_index(
        "ix_vendor_part_availabilities_vendor_id", "vendor_part_availabilities", ["vendor_id"]
    )
    op.create_index(
        "ix_vendor_part_availabilities_part_id", "vendor_part_availabilities", ["part_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vendor_part_availabilities_part_id", table_name="vendor_part_availabilities"
    )
    op.drop_index(
        "ix_vendor_part_availabilities_vendor_id", table_name="vendor_part_availabilities"
    )
    op.drop_index(
        "ix_vendor_part_availabilities_organization_id", table_name="vendor_part_availabilities"
    )
    op.drop_table("vendor_part_availabilities")

    op.drop_constraint("ck_vendors_reliability_score_range", "vendors", type_="check")
    op.drop_column("vendors", "reliability_score")
