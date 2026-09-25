"""Platform Control Plane: generic soft-delete lifecycle for Asset.

Adds deleted_at/deleted_by/deletion_reason/restored_at/restored_by to
`assets` (SoftDeleteMixin, see app/db/base.py) -- Asset is the pilot entity
for the platform-wide soft-delete/restore/permanent-delete architecture.
All five columns are nullable and additive: every existing row backfills to
NULL (never-deleted), so no existing data or query is affected until a row
is actually soft-deleted through the new deletion_service.

Revision ID: 0040
Revises: 0039
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "assets", sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("assets", sa.Column("deletion_reason", sa.String(500), nullable=True))
    op.add_column("assets", sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "assets", sa.Column("restored_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    # Tenant-facing asset reads always filter WHERE deleted_at IS NULL (see
    # asset_service.get_asset/list_assets) -- a partial index keyed on that
    # exact predicate keeps every such query cheap without indexing rows
    # that are already soft-deleted and excluded from those reads.
    op.create_index(
        "ix_assets_org_active",
        "assets",
        ["organization_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_assets_org_active", table_name="assets")
    op.drop_column("assets", "restored_by")
    op.drop_column("assets", "restored_at")
    op.drop_column("assets", "deletion_reason")
    op.drop_column("assets", "deleted_by")
    op.drop_column("assets", "deleted_at")
