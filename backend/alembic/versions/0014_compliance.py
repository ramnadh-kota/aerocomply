"""Regulatory requirements and compliance assessments (Milestone 3.12)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regulatory_requirements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authority", sa.String(length=16), nullable=False),
        sa.Column("requirement_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("compliance_time", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_regulatory_requirements_organization_id",
        "regulatory_requirements",
        ["organization_id"],
    )
    op.create_index(
        "ix_regulatory_requirements_requirement_number",
        "regulatory_requirements",
        ["requirement_number"],
    )

    op.create_table(
        "compliance_assessments",
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
            "requirement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_requirements.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("evaluated_at", sa.Date(), nullable=False),
        sa.Column(
            "evaluated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column(
            "overridden_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_compliance_assessments_organization_id",
        "compliance_assessments",
        ["organization_id"],
    )
    op.create_index(
        "ix_compliance_assessments_aircraft_id", "compliance_assessments", ["aircraft_id"]
    )
    op.create_index(
        "ix_compliance_assessments_requirement_id",
        "compliance_assessments",
        ["requirement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_compliance_assessments_requirement_id", table_name="compliance_assessments"
    )
    op.drop_index("ix_compliance_assessments_aircraft_id", table_name="compliance_assessments")
    op.drop_index(
        "ix_compliance_assessments_organization_id", table_name="compliance_assessments"
    )
    op.drop_table("compliance_assessments")

    op.drop_index(
        "ix_regulatory_requirements_requirement_number", table_name="regulatory_requirements"
    )
    op.drop_index(
        "ix_regulatory_requirements_organization_id", table_name="regulatory_requirements"
    )
    op.drop_table("regulatory_requirements")


