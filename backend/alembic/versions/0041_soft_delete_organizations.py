"""Platform Control Plane: organization-level deletion-request workflow.

Adds the same five SoftDeleteMixin columns (deleted_at/deleted_by/
deletion_reason/restored_at/restored_by) already added to `assets` in
migration 0040 -- Organization is the second soft-deletable entity. All
columns nullable/additive; every existing row backfills to NULL
(never-deletion-requested), so no existing data or query is affected until
an organization is actually soft-deleted through the new deletion_service
functions (request_organization_deletion / permanently_delete_organization).

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("organizations", sa.Column("deletion_reason", sa.String(500), nullable=True))
    op.add_column(
        "organizations", sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "organizations",
        sa.Column("restored_by", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "restored_by")
    op.drop_column("organizations", "restored_at")
    op.drop_column("organizations", "deletion_reason")
    op.drop_column("organizations", "deleted_by")
    op.drop_column("organizations", "deleted_at")
