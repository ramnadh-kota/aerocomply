"""Regulatory documents + link from RegulatoryRequirement (Milestone 3.13)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "regulatory_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("authority", sa.String(length=16), nullable=False),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("doc_number", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("revision", sa.String(length=32), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column(
            "source_status", sa.String(length=16), nullable=False, server_default="PUBLISHED"
        ),
        sa.Column("source_url", sa.String(length=512), nullable=True),
        sa.Column(
            "sync_status", sa.String(length=32), nullable=False, server_default="NOT_CONFIGURED"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_regulatory_documents_organization_id", "regulatory_documents", ["organization_id"]
    )
    op.create_index(
        "ix_regulatory_documents_doc_number", "regulatory_documents", ["doc_number"]
    )

    op.add_column(
        "regulatory_requirements",
        sa.Column(
            "regulatory_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("regulatory_documents.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("regulatory_requirements", "regulatory_document_id")

    op.drop_index("ix_regulatory_documents_doc_number", table_name="regulatory_documents")
    op.drop_index("ix_regulatory_documents_organization_id", table_name="regulatory_documents")
    op.drop_table("regulatory_documents")
