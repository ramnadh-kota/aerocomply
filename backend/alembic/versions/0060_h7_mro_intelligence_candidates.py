"""H7: MRO + Compliance + Readiness Intelligence Integration.

Revision ID: 0060
Revises: 0059
Create Date: 2026-09-28

Changes:
- Creates mro_intelligence_candidates table: the single new table H7 owns
  (a lifecycle-managed correlation/recommendation object). H7 is an
  integration layer over existing authoritative domains and does not
  introduce any other persisted state.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0060"
down_revision: str | None = "0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mro_intelligence_candidates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "component_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("components.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("candidate_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="MEDIUM"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column(
            "source_lineage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("operational_impact", sa.String(length=32), nullable=True),
        sa.Column("data_freshness", sa.String(length=32), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_mro_intelligence_candidates_organization_id", "mro_intelligence_candidates", ["organization_id"])
    op.create_index("ix_mro_intelligence_candidates_asset_id", "mro_intelligence_candidates", ["asset_id"])
    op.create_index("ix_mro_intelligence_candidates_component_id", "mro_intelligence_candidates", ["component_id"])
    op.create_index("ix_mro_intelligence_candidates_candidate_type", "mro_intelligence_candidates", ["candidate_type"])
    op.create_index("ix_mro_intelligence_candidates_status", "mro_intelligence_candidates", ["status"])
    op.create_index("ix_mro_intelligence_candidates_dedup_key", "mro_intelligence_candidates", ["dedup_key"])
    op.create_index("ix_mro_candidates_org_asset", "mro_intelligence_candidates", ["organization_id", "asset_id"])
    op.create_index("ix_mro_candidates_org_status", "mro_intelligence_candidates", ["organization_id", "status"])
    op.create_index("ix_mro_candidates_org_dedup_key", "mro_intelligence_candidates", ["organization_id", "dedup_key"])


def downgrade() -> None:
    op.drop_index("ix_mro_candidates_org_dedup_key", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_candidates_org_status", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_candidates_org_asset", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_intelligence_candidates_dedup_key", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_intelligence_candidates_status", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_intelligence_candidates_candidate_type", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_intelligence_candidates_component_id", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_intelligence_candidates_asset_id", table_name="mro_intelligence_candidates")
    op.drop_index("ix_mro_intelligence_candidates_organization_id", table_name="mro_intelligence_candidates")
    op.drop_table("mro_intelligence_candidates")
