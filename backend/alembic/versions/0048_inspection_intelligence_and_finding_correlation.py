"""M23: Inspection intelligence, finding correlation, and readiness gate integration.

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-27

Changes:
- Extends findings table with compliance correlation links:
  - compliance_obligation_id (FK to compliance_obligations.id)
  - regulatory_requirement_id (FK to regulatory_requirements.id)
  - safety_significance (VARCHAR(64))
  - compliance_relevance (VARCHAR(64))
- Extends inspection_requirements table with compliance correlation links:
  - compliance_obligation_id (FK to compliance_obligations.id)
  - regulatory_requirement_id (FK to regulatory_requirements.id)
- Creates supporting indexes.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Extend findings table
    op.add_column(
        "findings",
        sa.Column("compliance_obligation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("regulatory_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("safety_significance", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "findings",
        sa.Column("compliance_relevance", sa.String(length=64), nullable=True),
    )

    op.create_foreign_key(
        "fk_findings_compliance_obligation_id",
        "findings",
        "compliance_obligations",
        ["compliance_obligation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_findings_regulatory_requirement_id",
        "findings",
        "regulatory_requirements",
        ["regulatory_requirement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_findings_compliance_obligation_id",
        "findings",
        ["compliance_obligation_id"],
    )
    op.create_index(
        "ix_findings_regulatory_requirement_id",
        "findings",
        ["regulatory_requirement_id"],
    )

    # 2. Extend inspection_requirements table
    op.add_column(
        "inspection_requirements",
        sa.Column("compliance_obligation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "inspection_requirements",
        sa.Column("regulatory_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_inspection_requirements_compliance_obligation_id",
        "inspection_requirements",
        "compliance_obligations",
        ["compliance_obligation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inspection_requirements_regulatory_requirement_id",
        "inspection_requirements",
        "regulatory_requirements",
        ["regulatory_requirement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_inspection_requirements_compliance_obligation_id",
        "inspection_requirements",
        ["compliance_obligation_id"],
    )
    op.create_index(
        "ix_inspection_requirements_regulatory_requirement_id",
        "inspection_requirements",
        ["regulatory_requirement_id"],
    )


def downgrade() -> None:
    # 1. Downgrade inspection_requirements
    op.drop_index(
        "ix_inspection_requirements_regulatory_requirement_id",
        table_name="inspection_requirements",
    )
    op.drop_index(
        "ix_inspection_requirements_compliance_obligation_id",
        table_name="inspection_requirements",
    )
    op.drop_constraint(
        "fk_inspection_requirements_regulatory_requirement_id",
        "inspection_requirements",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_inspection_requirements_compliance_obligation_id",
        "inspection_requirements",
        type_="foreignkey",
    )
    op.drop_column("inspection_requirements", "regulatory_requirement_id")
    op.drop_column("inspection_requirements", "compliance_obligation_id")

    # 2. Downgrade findings
    op.drop_index("ix_findings_regulatory_requirement_id", table_name="findings")
    op.drop_index("ix_findings_compliance_obligation_id", table_name="findings")
    op.drop_constraint("fk_findings_regulatory_requirement_id", "findings", type_="foreignkey")
    op.drop_constraint("fk_findings_compliance_obligation_id", "findings", type_="foreignkey")
    op.drop_column("findings", "compliance_relevance")
    op.drop_column("findings", "safety_significance")
    op.drop_column("findings", "regulatory_requirement_id")
    op.drop_column("findings", "compliance_obligation_id")
