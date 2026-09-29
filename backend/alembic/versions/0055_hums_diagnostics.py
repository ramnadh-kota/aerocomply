"""H4: HUMS Diagnostics & Fault Isolation.

Revision ID: 0055
Revises: 0054
Create Date: 2026-09-28

Changes:
- Creates hums_diagnostic_candidates table: rule-based diagnostic
  hypotheses (never confirmed faults) generated from H3 feature-health
  evidence via versioned, in-code fault signatures. Unique per (org, asset,
  component, fault_code) so re-evaluation updates rather than duplicates.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hums_diagnostic_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sensor_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fault_code", sa.String(length=64), nullable=False),
        sa.Column("fault_name", sa.String(length=255), nullable=False),
        sa.Column("fault_domain", sa.String(length=32), nullable=False),
        sa.Column("diagnostic_method", sa.String(length=64), nullable=False, server_default="rule_based_signature_matching"),
        sa.Column("rule_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="CANDIDATE"),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("primary_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("supporting_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("contradicting_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rejection_reason", sa.String(length=500), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "asset_id", "component_id", "fault_code", name="uq_hums_diag_org_asset_component_fault"),
    )
    op.create_index("ix_hums_diag_candidates_organization_id", "hums_diagnostic_candidates", ["organization_id"])
    op.create_index("ix_hums_diag_candidates_asset_id", "hums_diagnostic_candidates", ["asset_id"])
    op.create_index("ix_hums_diag_candidates_component_id", "hums_diagnostic_candidates", ["component_id"])
    op.create_index("ix_hums_diag_candidates_fault_code", "hums_diagnostic_candidates", ["fault_code"])
    op.create_index("ix_hums_diag_org_asset_status", "hums_diagnostic_candidates", ["organization_id", "asset_id", "status"])


def downgrade() -> None:
    op.drop_table("hums_diagnostic_candidates")
