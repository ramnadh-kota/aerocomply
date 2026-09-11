"""Lisa conversation context (entity/reference resolution memory)

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lisa_conversation_contexts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("current_aircraft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_work_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_part_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_part_requirement_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_procurement_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_vendor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_purchase_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_technician_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_aog_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recent_entities", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("previous_question", sa.Text(), nullable=True),
        sa.Column("recent_questions", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("context_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_lisa_context_org_user"),
    )
    op.create_index(
        "ix_lisa_conversation_contexts_organization_id",
        "lisa_conversation_contexts",
        ["organization_id"],
    )
    op.create_index(
        "ix_lisa_conversation_contexts_user_id", "lisa_conversation_contexts", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lisa_conversation_contexts_user_id", table_name="lisa_conversation_contexts"
    )
    op.drop_index(
        "ix_lisa_conversation_contexts_organization_id", table_name="lisa_conversation_contexts"
    )
    op.drop_table("lisa_conversation_contexts")
