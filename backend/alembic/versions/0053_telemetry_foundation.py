"""M13: Telemetry foundation, external asset mappings, and telemetry event logs.

Revision ID: 0053
Revises: 0052
Create Date: 2026-09-27

Changes:
- Creates `external_asset_mappings` table for tenant-scoped external provider asset ID resolution.
- Creates `telemetry_event_logs` table for deterministic idempotency and forensic provenance tracking.
All changes are strictly additive and fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053"
down_revision: str | None = "0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "external_asset_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("external_asset_id", sa.String(length=128), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_model", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "source_system",
            "external_asset_id",
            name="uq_ext_asset_map_org_source_extid",
        ),
    )
    op.create_index(
        "ix_ext_asset_map_org_source",
        "external_asset_mappings",
        ["organization_id", "source_system"],
    )
    op.create_index(
        "ix_ext_asset_map_org_asset",
        "external_asset_mappings",
        ["organization_id", "asset_id"],
    )

    op.create_table(
        "telemetry_event_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("source_asset_id", sa.String(length=128), nullable=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("flight_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_version", sa.String(length=32), nullable=False, server_default="1.0"),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            nullable=False,
            server_default="RECEIVED",
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("readings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["flight_id"], ["flights.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id",
            "source_system",
            "source_event_id",
            name="uq_telemetry_event_org_source_eventid",
        ),
    )
    op.create_index(
        "ix_telemetry_event_org_status",
        "telemetry_event_logs",
        ["organization_id", "processing_status"],
    )
    op.create_index(
        "ix_telemetry_event_org_ts",
        "telemetry_event_logs",
        ["organization_id", "event_timestamp"],
    )
    op.create_index(
        "ix_telemetry_event_logs_idempotency_key",
        "telemetry_event_logs",
        ["idempotency_key"],
    )


def downgrade() -> None:
    op.drop_table("telemetry_event_logs")
    op.drop_table("external_asset_mappings")
