"""M20.2: general Finding/Disposition domain model.

Adds `findings` (tenant-scoped, traceable to an aircraft OR a generic asset
via the same dual aircraft_id/asset_id pattern already used on WorkOrder,
optionally to a component/inspection requirement/work order/task) and
`finding_dispositions` (a Finding's disposition history -- corrective
action, no-action-required, or deferred, with an optional evidence link and
closure metadata). See app/models/finding.py for the full design rationale.

This is additive only: no existing table is altered.

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("aircraft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("inspection_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("work_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column(
            "discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("discovered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("responsible_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["aircraft_id"], ["aircraft.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["component_id"], ["components.id"]),
        sa.ForeignKeyConstraint(["inspection_requirement_id"], ["inspection_requirements.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_orders.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_organization_id", "findings", ["organization_id"])
    op.create_index("ix_findings_aircraft_id", "findings", ["aircraft_id"])
    op.create_index("ix_findings_asset_id", "findings", ["asset_id"])
    op.create_index("ix_findings_component_id", "findings", ["component_id"])
    op.create_index(
        "ix_findings_inspection_requirement_id", "findings", ["inspection_requirement_id"]
    )
    op.create_index("ix_findings_work_order_id", "findings", ["work_order_id"])
    op.create_index("ix_findings_task_id", "findings", ["task_id"])
    op.alter_column("findings", "status", server_default=None)

    op.create_table(
        "finding_dispositions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disposition_type", sa.String(length=32), nullable=False),
        sa.Column("corrective_action", sa.Text(), nullable=True),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"]),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_finding_dispositions_organization_id", "finding_dispositions", ["organization_id"]
    )
    op.create_index("ix_finding_dispositions_finding_id", "finding_dispositions", ["finding_id"])


def downgrade() -> None:
    op.drop_index("ix_finding_dispositions_finding_id", table_name="finding_dispositions")
    op.drop_index("ix_finding_dispositions_organization_id", table_name="finding_dispositions")
    op.drop_table("finding_dispositions")

    op.drop_index("ix_findings_task_id", table_name="findings")
    op.drop_index("ix_findings_work_order_id", table_name="findings")
    op.drop_index("ix_findings_inspection_requirement_id", table_name="findings")
    op.drop_index("ix_findings_component_id", table_name="findings")
    op.drop_index("ix_findings_asset_id", table_name="findings")
    op.drop_index("ix_findings_aircraft_id", table_name="findings")
    op.drop_index("ix_findings_organization_id", table_name="findings")
    op.drop_table("findings")
