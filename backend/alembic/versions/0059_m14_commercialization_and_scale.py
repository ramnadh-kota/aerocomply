"""M14: Commercialization Platform, Edge Hardware, and Retention Policies.

Revision ID: 0059
Revises: 0058
Create Date: 2026-09-28

Changes:
- Adds onboarding_stage, logo_url, and primary_color to organizations.
- Creates edge_devices table for hardware telemetry provenance and gateway device tracking.
- Creates tenant_retention_policies table for tenant data lifecycle management.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0059"
down_revision: str | None = "0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add onboarding and branding fields to organizations
    op.add_column(
        "organizations",
        sa.Column("onboarding_stage", sa.String(length=32), nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "organizations",
        sa.Column("logo_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("primary_color", sa.String(length=32), nullable=True),
    )

    # 2. Create edge_devices table
    op.create_table(
        "edge_devices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("gateway_id", sa.String(length=128), nullable=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("device_type", sa.String(length=64), nullable=False, server_default="SENSOR_NODE"),
        sa.Column("firmware_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "device_id", name="uq_edge_devices_org_device_id"),
    )
    op.create_index("ix_edge_devices_org_status", "edge_devices", ["organization_id", "status"])
    op.create_index("ix_edge_devices_asset", "edge_devices", ["asset_id"])

    # 3. Create tenant_retention_policies table
    op.create_table(
        "tenant_retention_policies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data_category", sa.String(length=64), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="2555"),  # 7 years standard
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "data_category", name="uq_retention_policies_org_category"),
    )
    op.create_index("ix_retention_policies_org", "tenant_retention_policies", ["organization_id"])


def downgrade() -> None:
    op.drop_table("tenant_retention_policies")
    op.drop_table("edge_devices")
    op.drop_column("organizations", "primary_color")
    op.drop_column("organizations", "logo_url")
    op.drop_column("organizations", "onboarding_stage")
