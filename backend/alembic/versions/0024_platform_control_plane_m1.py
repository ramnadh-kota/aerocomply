"""Platform Control Plane M1: plans, plan_features, subscriptions,
tenant_feature_overrides, tenant_usage_limits

Pure database/domain foundation for tenant subscriptions and feature
entitlements -- no API, no service layer, no billing, no usage metering, no
entitlement-evaluation engine. See
docs/PLATFORM_CONTROL_PLANE_ARCHITECTURE.md, "M1 Implementation" section.

Written by hand (not `alembic revision --autogenerate`) because autogenerate
currently fails on this codebase for an unrelated, pre-existing reason:
app/models/warehouse.py (which defines the `locations` table referenced by
parts.location_id) is not imported in app/models/__init__.py, so
SQLAlchemy's metadata is incomplete when alembic's autogenerate walks FKs.
That is out of scope for this migration and left untouched.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("code", name="uq_plans_code"),
    )
    op.create_index("ix_plans_code", "plans", ["code"])

    op.create_table(
        "plan_features",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name="fk_plan_features_plan_id_plans", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "plan_id", "feature_key", name="uq_plan_features_plan_id_feature_key"
        ),
    )
    op.create_index("ix_plan_features_plan_id", "plan_features", ["plan_id"])

    op.create_table(
        "subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_subscriptions_plan_id_plans",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_subscriptions_organization_id", "subscriptions", ["organization_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index(
        "ix_subscriptions_org_status_starts_at",
        "subscriptions",
        ["organization_id", "status", "starts_at"],
    )

    op.create_table(
        "tenant_feature_overrides",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_tenant_feature_overrides_created_by_user_id_users",
        ),
    )
    op.create_index(
        "ix_tenant_feature_overrides_organization_id",
        "tenant_feature_overrides",
        ["organization_id"],
    )
    op.create_index(
        "ix_tenant_feature_overrides_feature_key", "tenant_feature_overrides", ["feature_key"]
    )

    op.create_table(
        "tenant_usage_limits",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("limit_key", sa.String(128), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("is_unlimited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "organization_id",
            "feature_key",
            "limit_key",
            name="uq_tenant_usage_limits_org_feature_limit",
        ),
    )
    op.create_index(
        "ix_tenant_usage_limits_organization_id", "tenant_usage_limits", ["organization_id"]
    )
    op.create_index(
        "ix_tenant_usage_limits_feature_key", "tenant_usage_limits", ["feature_key"]
    )


def downgrade() -> None:
    op.drop_table("tenant_usage_limits")
    op.drop_table("tenant_feature_overrides")
    op.drop_table("subscriptions")
    op.drop_table("plan_features")
    op.drop_table("plans")
