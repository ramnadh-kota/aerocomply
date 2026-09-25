"""Platform Control Plane: work-order-level soft-delete/restore.

Adds the same five SoftDeleteMixin columns (deleted_at/deleted_by/
deletion_reason/restored_at/restored_by) already added to `assets` in
migration 0040 and `organizations` in migration 0041 -- WorkOrder is the
third soft-deletable entity (lifecycle_policy.py's WORKORDER entry,
category A). All columns nullable/additive; every existing row backfills to
NULL (never-deleted), so no existing data or query is affected until a work
order is actually soft-deleted through the new deletion_service functions
(soft_delete_work_order / permanently_delete_work_order).

Deliberately does NOT touch any FK ondelete value on the 8 dependent tables
(Task, PartRequirement, AogEvent, DeferredItem, Finding,
InspectionRequirement, MaintenanceRequirement, ProcurementRequest) -- those
remain whatever they already were (Postgres default NO ACTION); permanent
deletion of a WorkOrder is guarded by an application-level dependency check
(see deletion_service.permanently_delete_work_order), not a DB constraint.

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: str | None = "0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_orders", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "work_orders",
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("work_orders", sa.Column("deletion_reason", sa.String(500), nullable=True))
    op.add_column(
        "work_orders", sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "work_orders",
        sa.Column("restored_by", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_orders", "restored_by")
    op.drop_column("work_orders", "restored_at")
    op.drop_column("work_orders", "deletion_reason")
    op.drop_column("work_orders", "deleted_by")
    op.drop_column("work_orders", "deleted_at")
