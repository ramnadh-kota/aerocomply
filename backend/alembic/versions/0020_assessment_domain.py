"""MRO Assessment & Impact Intelligence domain

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False, server_default="FLEET"),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_assessments_organization_id", "assessments", ["organization_id"])

    op.create_table(
        "assessment_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessments.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("maturity_band", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_finding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_assessment_snapshots_organization_id", "assessment_snapshots", ["organization_id"]
    )
    op.create_index(
        "ix_assessment_snapshots_assessment_id", "assessment_snapshots", ["assessment_id"]
    )

    op.create_table(
        "assessment_findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_snapshots.id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("materiality_score", sa.Float(), nullable=False),
        sa.Column("complexity_band", sa.String(length=32), nullable=False),
        sa.Column("dependency_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impact_dimensions", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("priority_rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_assessment_findings_organization_id", "assessment_findings", ["organization_id"]
    )
    op.create_index("ix_assessment_findings_snapshot_id", "assessment_findings", ["snapshot_id"])

    op.create_table(
        "assessment_risks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_findings.id"),
            nullable=True,
        ),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("likelihood", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("owner_role", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_assessment_risks_organization_id", "assessment_risks", ["organization_id"])
    op.create_index("ix_assessment_risks_snapshot_id", "assessment_risks", ["snapshot_id"])

    op.create_table(
        "assessment_gaps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_findings.id"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("expected_condition", sa.Text(), nullable=False),
        sa.Column("current_condition", sa.Text(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_assessment_gaps_organization_id", "assessment_gaps", ["organization_id"])
    op.create_index("ix_assessment_gaps_snapshot_id", "assessment_gaps", ["snapshot_id"])

    op.create_table(
        "assessment_recommendations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_findings.id"),
            nullable=True,
        ),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("responsible_role", sa.String(length=64), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_assessment_recommendations_organization_id",
        "assessment_recommendations",
        ["organization_id"],
    )
    op.create_index(
        "ix_assessment_recommendations_snapshot_id", "assessment_recommendations", ["snapshot_id"]
    )

    op.create_table(
        "assessment_roadmap_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_findings.id"),
            nullable=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PLANNED"),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("prerequisite_sequence_numbers", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("owner_role", sa.String(length=64), nullable=True),
        sa.Column(
            "estimated_effort_band", sa.String(length=32), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("effort_confidence", sa.String(length=32), nullable=False, server_default="LOW"),
        sa.Column("expected_impact", sa.Text(), nullable=False),
        sa.Column("risk_if_delayed", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_assessment_roadmap_items_organization_id",
        "assessment_roadmap_items",
        ["organization_id"],
    )
    op.create_index(
        "ix_assessment_roadmap_items_snapshot_id", "assessment_roadmap_items", ["snapshot_id"]
    )

    op.create_table(
        "assessment_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_snapshots.id"),
            nullable=False,
        ),
        sa.Column("metric_key", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_assessment_metrics_organization_id", "assessment_metrics", ["organization_id"]
    )
    op.create_index("ix_assessment_metrics_snapshot_id", "assessment_metrics", ["snapshot_id"])


def downgrade() -> None:
    op.drop_table("assessment_metrics")
    op.drop_table("assessment_roadmap_items")
    op.drop_table("assessment_recommendations")
    op.drop_table("assessment_gaps")
    op.drop_table("assessment_risks")
    op.drop_table("assessment_findings")
    op.drop_table("assessment_snapshots")
    op.drop_table("assessments")
