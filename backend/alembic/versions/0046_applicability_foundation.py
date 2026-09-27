"""0046: Applicability Foundation, Condition Trees, and Immutable Evaluations.

Milestone D2-1 (Developer 2):
Creates core tables for deterministic aerospace applicability evaluation:
- applicability_rules
- applicability_conditions
- applicability_evaluations

Revision ID: 0046
Revises: 0045
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create applicability_rules table
    op.create_table(
        "applicability_rules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("regulatory_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("root_condition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_applicability_rules_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["regulatory_requirement_id"],
            ["regulatory_requirements.id"],
            name="fk_applicability_rules_reg_req",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("organization_id", "rule_code", name="uq_applicability_rules_org_code"),
    )
    op.create_index("ix_applicability_rules_organization_id", "applicability_rules", ["organization_id"])
    op.create_index("ix_applicability_rules_rule_code", "applicability_rules", ["rule_code"])
    op.create_index(
        "ix_applicability_rules_regulatory_requirement_id",
        "applicability_rules",
        ["regulatory_requirement_id"],
    )

    # 2. Create applicability_conditions table
    op.create_table(
        "applicability_conditions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_condition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("condition_type", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_applicability_conditions_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["applicability_rules.id"],
            name="fk_applicability_conditions_rule",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_condition_id"],
            ["applicability_conditions.id"],
            name="fk_applicability_conditions_parent",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_applicability_conditions_organization_id", "applicability_conditions", ["organization_id"])
    op.create_index("ix_applicability_conditions_rule_id", "applicability_conditions", ["rule_id"])
    op.create_index("ix_applicability_conditions_parent_condition_id", "applicability_conditions", ["parent_condition_id"])

    # Add foreign key for root_condition_id on applicability_rules (circular ref with conditions)
    op.create_foreign_key(
        "fk_applicability_rules_root_condition",
        "applicability_rules",
        "applicability_conditions",
        ["root_condition_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )

    # 3. Create applicability_evaluations table
    op.create_table(
        "applicability_evaluations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aircraft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("evaluated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("system_result", sa.String(32), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("configuration_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reasoning_trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_applicability_evaluations_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["applicability_rules.id"],
            name="fk_applicability_evaluations_rule",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["aircraft_id"],
            ["aircraft.id"],
            name="fk_applicability_evaluations_aircraft",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name="fk_applicability_evaluations_asset",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["evaluated_by_user_id"],
            ["users.id"],
            name="fk_applicability_evaluations_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_applicability_evaluations_organization_id", "applicability_evaluations", ["organization_id"])
    op.create_index("ix_applicability_evaluations_rule_id", "applicability_evaluations", ["rule_id"])
    op.create_index("ix_applicability_evaluations_aircraft_id", "applicability_evaluations", ["aircraft_id"])
    op.create_index("ix_applicability_evaluations_asset_id", "applicability_evaluations", ["asset_id"])
    op.create_index("ix_applicability_evaluations_evaluated_at", "applicability_evaluations", ["evaluated_at"])


def downgrade() -> None:
    op.drop_table("applicability_evaluations")
    op.drop_constraint("fk_applicability_rules_root_condition", "applicability_rules", type_="foreignkey")
    op.drop_table("applicability_conditions")
    op.drop_table("applicability_rules")
