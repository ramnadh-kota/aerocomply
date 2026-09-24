"""WorkOrder lifecycle foundation: soft-delete/restore columns + updated_at.

Schema-only foundation for the WorkOrder soft-delete/restore governance
feature. Adds the reusable LifecycleMixin columns (deleted_at, deleted_by,
restored_at, restored_by) to work_orders only -- no other table is touched,
and no service/API/permission/audit behavior is added in this migration.

deleted_at IS NULL is the single authoritative condition for "currently
active"; existing rows are unaffected (all four lifecycle columns default to
NULL, i.e. active) and gain a server-defaulted updated_at.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_orders",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "work_orders",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "work_orders",
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "work_orders",
        sa.Column("restored_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "work_orders",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_foreign_key(
        "fk_work_orders_deleted_by_users",
        "work_orders",
        "users",
        ["deleted_by"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_work_orders_restored_by_users",
        "work_orders",
        "users",
        ["restored_by"],
        ["id"],
    )

    op.create_index(
        "ix_work_orders_organization_id_deleted_at",
        "work_orders",
        ["organization_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_work_orders_organization_id_deleted_at", table_name="work_orders")

    op.drop_constraint("fk_work_orders_restored_by_users", "work_orders", type_="foreignkey")
    op.drop_constraint("fk_work_orders_deleted_by_users", "work_orders", type_="foreignkey")

    op.drop_column("work_orders", "updated_at")
    op.drop_column("work_orders", "restored_by")
    op.drop_column("work_orders", "restored_at")
    op.drop_column("work_orders", "deleted_by")
    op.drop_column("work_orders", "deleted_at")
