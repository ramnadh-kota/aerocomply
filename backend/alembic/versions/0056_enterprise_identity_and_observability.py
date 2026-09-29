"""M13 Phase 4 & 5: Enterprise Identity (SSO / Entra ID) and Operational Incident Observability.

Revision ID: 0056
Revises: 0055
Create Date: 2026-09-28

Changes:
- Creates sso_configurations table: Tenant-level OIDC/Entra ID SSO integration settings & role mappings.
- Creates external_identity_mappings table: Deterministic 1-to-1 linkage between external IdP subjects and KOTA Users.
- Creates operational_incidents table: Operational & infrastructure incident tracking (P0-P3) for production hypercare.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0056"
down_revision: str | None = "0055"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. SSO Configurations Table
    op.create_table(
        "sso_configurations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False, server_default="ENTRA_ID"),
        sa.Column("issuer_url", sa.String(length=512), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=512), nullable=True),
        sa.Column("tenant_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("enforce_sso", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("default_role", sa.String(length=64), nullable=False, server_default="VIEWER"),
        sa.Column("domain_hint", sa.String(length=255), nullable=True),
        sa.Column(
            "role_mappings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("organization_id", "provider_type", name="uq_sso_config_org_provider"),
    )
    op.create_index("ix_sso_config_org", "sso_configurations", ["organization_id"])

    # 2. External Identity Mappings Table
    op.create_table(
        "external_identity_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False, server_default="ENTRA_ID"),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_authenticated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider_type",
            "subject",
            name="uq_ext_identity_org_provider_subject",
        ),
    )
    op.create_index("ix_ext_identity_org_user", "external_identity_mappings", ["organization_id", "user_id"])
    op.create_index("ix_ext_identity_email", "external_identity_mappings", ["email"])

    # 3. Operational Incidents Table
    op.create_table(
        "operational_incidents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="P2"),
        sa.Column("service_name", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="OPEN"),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_op_incident_org_status", "operational_incidents", ["organization_id", "status"])
    op.create_index("ix_op_incident_org_severity", "operational_incidents", ["organization_id", "severity"])
    op.create_index("ix_op_incident_service", "operational_incidents", ["service_name"])


def downgrade() -> None:
    op.drop_index("ix_op_incident_service", table_name="operational_incidents")
    op.drop_index("ix_op_incident_org_severity", table_name="operational_incidents")
    op.drop_index("ix_op_incident_org_status", table_name="operational_incidents")
    op.drop_table("operational_incidents")

    op.drop_index("ix_ext_identity_email", table_name="external_identity_mappings")
    op.drop_index("ix_ext_identity_org_user", table_name="external_identity_mappings")
    op.drop_table("external_identity_mappings")

    op.drop_index("ix_sso_config_org", table_name="sso_configurations")
    op.drop_table("sso_configurations")
