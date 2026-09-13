"""M14: approval_requests table for governance approvals over expansive
tenant entitlement mutations.

Written by hand for the same reason 0024 was: autogenerate is currently
broken on this codebase (app/models/warehouse.py's Location model is not
imported early enough for FK metadata resolution) -- unrelated and out of
scope here.

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-14

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("requested_enabled", sa.Boolean(), nullable=True),
        sa.Column("limit_key", sa.String(128), nullable=True),
        sa.Column("requested_limit_value", sa.Integer(), nullable=True),
        sa.Column("requested_is_unlimited", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_approval_requests_requested_by_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name="fk_approval_requests_reviewed_by_user_id_users",
        ),
    )
    op.create_index(
        "ix_approval_requests_organization_id", "approval_requests", ["organization_id"]
    )
    op.create_index("ix_approval_requests_request_type", "approval_requests", ["request_type"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index(
        "ix_approval_requests_status_created_at",
        "approval_requests",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
