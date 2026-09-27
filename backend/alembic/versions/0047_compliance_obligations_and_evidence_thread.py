"""0047: Compliance Obligations and Evidence Digital Thread.

Milestone D2-2 (Developer 2):
Creates compliance obligations domain model and extends evidence model into a first-class digital thread:
- Creates compliance_obligations table
- Extends evidence table with linkages to compliance obligations, requirements, assets, aircraft, components, work orders, findings, and inspection requirements
- Adds title, evidence_type, verification_status, provenance, and verification metadata to evidence
- Makes evidence.task_id nullable to support non-task evidence

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create compliance_obligations table
    op.create_table(
        "compliance_obligations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aircraft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applicability_evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="NOT_EVALUATED"),
        sa.Column("priority", sa.String(32), nullable=False, server_default="MEDIUM"),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("recurrence", sa.String(64), nullable=True),
        sa.Column("responsible_role", sa.String(64), nullable=True),
        sa.Column("assigned_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("required_action", sa.Text(), nullable=True),
        sa.Column("evidence_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["regulatory_requirements.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["applicability_rules.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["aircraft_id"],
            ["aircraft.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["applicability_evaluation_id"],
            ["applicability_evaluations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_compliance_obligations_organization_id",
        "compliance_obligations",
        ["organization_id"],
    )
    op.create_index(
        "ix_compliance_obligations_requirement_id",
        "compliance_obligations",
        ["requirement_id"],
    )
    op.create_index(
        "ix_compliance_obligations_rule_id",
        "compliance_obligations",
        ["rule_id"],
    )
    op.create_index(
        "ix_compliance_obligations_asset_id",
        "compliance_obligations",
        ["asset_id"],
    )
    op.create_index(
        "ix_compliance_obligations_aircraft_id",
        "compliance_obligations",
        ["aircraft_id"],
    )
    op.create_index(
        "ix_compliance_obligations_status",
        "compliance_obligations",
        ["status"],
    )
    op.create_index(
        "ix_compliance_obligations_due_date",
        "compliance_obligations",
        ["due_date"],
    )

    # Partial unique indexes for idempotent obligation management per asset/aircraft
    op.create_index(
        "uq_compliance_obligations_org_asset_req",
        "compliance_obligations",
        ["organization_id", "asset_id", "requirement_id"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL"),
    )
    op.create_index(
        "uq_compliance_obligations_org_ac_req",
        "compliance_obligations",
        ["organization_id", "aircraft_id", "requirement_id"],
        unique=True,
        postgresql_where=sa.text("aircraft_id IS NOT NULL AND asset_id IS NULL"),
    )

    # 2. Extend evidence table for first-class digital thread
    # 2a. Make task_id nullable so non-task evidence can be created
    op.alter_column(
        "evidence",
        "task_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # 2b. Add new relational linkage columns
    op.add_column(
        "evidence",
        sa.Column("compliance_obligation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("regulatory_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("aircraft_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("inspection_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2c. Add descriptive & verification metadata columns
    op.add_column(
        "evidence",
        sa.Column("title", sa.String(255), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("evidence_type", sa.String(64), nullable=False, server_default="INSPECTION_RECORD"),
    )
    op.add_column(
        "evidence",
        sa.Column("source", sa.String(255), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("verification_status", sa.String(32), nullable=False, server_default="UNVERIFIED"),
    )
    op.add_column(
        "evidence",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("verifier_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("verification_notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "evidence",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 2d. Foreign keys on evidence table
    op.create_foreign_key(
        "fk_evidence_compliance_obligation_id",
        "evidence",
        "compliance_obligations",
        ["compliance_obligation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_regulatory_requirement_id",
        "evidence",
        "regulatory_requirements",
        ["regulatory_requirement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_asset_id",
        "evidence",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_aircraft_id",
        "evidence",
        "aircraft",
        ["aircraft_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_component_id",
        "evidence",
        "components",
        ["component_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_inspection_requirement_id",
        "evidence",
        "inspection_requirements",
        ["inspection_requirement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_finding_id",
        "evidence",
        "findings",
        ["finding_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_work_order_id",
        "evidence",
        "work_orders",
        ["work_order_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_verifier_user_id",
        "evidence",
        "users",
        ["verifier_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 2e. Indexes on evidence
    op.create_index(
        "ix_evidence_compliance_obligation_id",
        "evidence",
        ["compliance_obligation_id"],
    )
    op.create_index(
        "ix_evidence_regulatory_requirement_id",
        "evidence",
        ["regulatory_requirement_id"],
    )
    op.create_index(
        "ix_evidence_asset_id",
        "evidence",
        ["asset_id"],
    )
    op.create_index(
        "ix_evidence_aircraft_id",
        "evidence",
        ["aircraft_id"],
    )
    op.create_index(
        "ix_evidence_verification_status",
        "evidence",
        ["verification_status"],
    )


def downgrade() -> None:
    # 1. Drop evidence indexes and foreign keys
    op.drop_index("ix_evidence_verification_status", table_name="evidence")
    op.drop_index("ix_evidence_aircraft_id", table_name="evidence")
    op.drop_index("ix_evidence_asset_id", table_name="evidence")
    op.drop_index("ix_evidence_regulatory_requirement_id", table_name="evidence")
    op.drop_index("ix_evidence_compliance_obligation_id", table_name="evidence")

    op.drop_constraint("fk_evidence_verifier_user_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_work_order_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_finding_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_inspection_requirement_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_component_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_aircraft_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_asset_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_regulatory_requirement_id", "evidence", type_="foreignkey")
    op.drop_constraint("fk_evidence_compliance_obligation_id", "evidence", type_="foreignkey")

    # Drop evidence added columns
    op.drop_column("evidence", "updated_at")
    op.drop_column("evidence", "provenance")
    op.drop_column("evidence", "verification_notes")
    op.drop_column("evidence", "verifier_user_id")
    op.drop_column("evidence", "verified_at")
    op.drop_column("evidence", "verification_status")
    op.drop_column("evidence", "captured_at")
    op.drop_column("evidence", "source")
    op.drop_column("evidence", "evidence_type")
    op.drop_column("evidence", "description")
    op.drop_column("evidence", "title")
    op.drop_column("evidence", "work_order_id")
    op.drop_column("evidence", "finding_id")
    op.drop_column("evidence", "inspection_requirement_id")
    op.drop_column("evidence", "component_id")
    op.drop_column("evidence", "aircraft_id")
    op.drop_column("evidence", "asset_id")
    op.drop_column("evidence", "regulatory_requirement_id")
    op.drop_column("evidence", "compliance_obligation_id")

    # Restore task_id non-null (clean up any NULL task_id first if necessary)
    op.alter_column(
        "evidence",
        "task_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    # 2. Drop compliance_obligations table
    op.drop_index("uq_compliance_obligations_org_ac_req", table_name="compliance_obligations")
    op.drop_index("uq_compliance_obligations_org_asset_req", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_due_date", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_status", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_aircraft_id", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_asset_id", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_rule_id", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_requirement_id", table_name="compliance_obligations")
    op.drop_index("ix_compliance_obligations_organization_id", table_name="compliance_obligations")
    op.drop_table("compliance_obligations")
