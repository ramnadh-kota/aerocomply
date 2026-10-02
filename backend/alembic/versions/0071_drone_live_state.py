"""0071: latest drone live state (C4).

Revises: 0070
Additive table. One row per drone asset; PostgreSQL is the authority and the row is a derived latest-state cache that
can be rebuilt from telemetry_event_logs. Downgrade drops the table (no other data depends on it).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0071"
down_revision: str | None = "0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "drone_live_state",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("data_source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", sa.String(128), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_drone_live_state_organization_id", "drone_live_state", ["organization_id"])
    op.create_index("ix_drone_live_state_org_received", "drone_live_state", ["organization_id", "last_received_at"])


def downgrade() -> None:
    op.drop_index("ix_drone_live_state_org_received", table_name="drone_live_state")
    op.drop_index("ix_drone_live_state_organization_id", table_name="drone_live_state")
    op.drop_table("drone_live_state")
