"""0072: geofences, geofence version history and live rule state (C5).

Revises: 0071
Additive tables only. `geofences` is tenant configuration (advisory operational zones); `geofence_versions` is its
immutable history; `live_rule_state` is derived evaluator memory (rebuildable). Alerts themselves live in the existing
M7 table `proactive_signal_records` -- this migration adds no alert table. Downgrade drops the three tables
(configured geofences and their history would be lost; alerts already raised in M7 are kept).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0072"
down_revision: str | None = "0071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "geofences",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("geometry_type", sa.String(16), nullable=False),
        sa.Column("geometry", postgresql.JSONB(), nullable=False),
        sa.Column("altitude_reference", sa.String(16), nullable=False, server_default="HOME_RELATIVE"),
        sa.Column("alt_min_m", sa.Float(), nullable=True),
        sa.Column("alt_max_m", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="HIGH"),
        sa.Column("proximity_buffer_m", sa.Float(), nullable=False, server_default="0"),
        sa.Column("boundary_tolerance_m", sa.Float(), nullable=False, server_default="5"),
        sa.Column("confirm_count", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("asset_ids", postgresql.JSONB(), nullable=True),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('RESTRICTED','CAUTION','OPERATING_AREA')", name="ck_geofence_kind"),
        sa.CheckConstraint("geometry_type IN ('CIRCLE','POLYGON')", name="ck_geofence_geometry_type"),
        sa.CheckConstraint("altitude_reference IN ('MSL','HOME_RELATIVE')", name="ck_geofence_alt_ref"),
        sa.CheckConstraint("severity IN ('CRITICAL','HIGH','MEDIUM','LOW')", name="ck_geofence_severity"),
        sa.CheckConstraint("alt_min_m IS NULL OR alt_max_m IS NULL OR alt_min_m < alt_max_m", name="ck_geofence_alt_range"),
        sa.CheckConstraint("proximity_buffer_m >= 0 AND boundary_tolerance_m >= 0", name="ck_geofence_distances"),
        sa.CheckConstraint("confirm_count BETWEEN 1 AND 10", name="ck_geofence_confirm"),
        sa.CheckConstraint("active_from IS NULL OR active_until IS NULL OR active_from < active_until", name="ck_geofence_window"),
    )
    op.create_index("ix_geofences_organization_id", "geofences", ["organization_id"])
    op.create_index("ix_geofences_org_active", "geofences", ["organization_id", "is_active"])

    op.create_table(
        "geofence_versions",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("geofence_id", UUID, sa.ForeignKey("geofences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(24), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("geofence_id", "version", name="uq_geofence_version"),
    )
    op.create_index("ix_geofence_versions_organization_id", "geofence_versions", ["organization_id"])
    op.create_index("ix_geofence_versions_geofence_id", "geofence_versions", ["geofence_id"])

    op.create_table(
        "live_rule_state",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("asset_id", UUID, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_key", sa.String(160), nullable=False),
        sa.Column("geofence_id", UUID, sa.ForeignKey("geofences.id", ondelete="CASCADE"), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="UNKNOWN"),
        sa.Column("candidate_state", sa.String(16), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("condition", sa.String(24), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signal_id", UUID, sa.ForeignKey("proactive_signal_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rule_version", sa.Integer(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_signed_distance_m", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "asset_id", "rule_key", name="uq_live_rule_state"),
    )
    op.create_index("ix_live_rule_state_organization_id", "live_rule_state", ["organization_id"])
    op.create_index("ix_live_rule_state_asset_id", "live_rule_state", ["asset_id"])
    op.create_index("ix_live_rule_state_geofence_id", "live_rule_state", ["geofence_id"])


def downgrade() -> None:
    for ix in ("ix_live_rule_state_geofence_id", "ix_live_rule_state_asset_id", "ix_live_rule_state_organization_id"):
        op.drop_index(ix, table_name="live_rule_state")
    op.drop_table("live_rule_state")
    op.drop_index("ix_geofence_versions_geofence_id", table_name="geofence_versions")
    op.drop_index("ix_geofence_versions_organization_id", table_name="geofence_versions")
    op.drop_table("geofence_versions")
    op.drop_index("ix_geofences_org_active", table_name="geofences")
    op.drop_index("ix_geofences_organization_id", table_name="geofences")
    op.drop_table("geofences")
