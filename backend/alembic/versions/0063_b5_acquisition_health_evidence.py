"""0063: B5/B14 — acquisition health evidence on data_sources.

Revises: 0062
Create Date: 2026-09-30

Adds the runtime evidence a source's health must be derived from (previously only
total_events_ingested / total_events_rejected / consecutive_failures existed, so
staleness, duplicates, packet loss and latency were invisible):

  last_seen_at              last time ANY data or attempt arrived (success or failure)
  last_success_at           last time at least one event was accepted
  last_failure_at           last time an acquisition attempt failed
  last_error                short, sanitised description of the last failure
  total_events_duplicate    events dropped as duplicates (idempotency / sequence)
  total_events_quarantined  events held because the asset could not be resolved uniquely
  total_packets_lost        sequence numbers skipped by the link (MAVLink loss)
  latency_ms_avg            exponentially-weighted mean of (received_at - event_timestamp)

Existing rows: counters default to 0, timestamps NULL (=> "no evidence yet", never
fabricated). Downgrade drops the columns; no other table is touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0063"
down_revision: str | None = "0062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("last_seen_at", "last_success_at", "last_failure_at"):
        op.add_column("data_sources", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("data_sources", sa.Column("last_error", sa.String(length=512), nullable=True))
    for name in ("total_events_duplicate", "total_events_quarantined", "total_packets_lost"):
        op.add_column(
            "data_sources", sa.Column(name, sa.Integer(), nullable=False, server_default="0")
        )
    op.add_column("data_sources", sa.Column("latency_ms_avg", sa.Float(), nullable=True))
    # Existing successes already recorded in last_acquisition_at are the same fact.
    op.execute("UPDATE data_sources SET last_success_at = last_acquisition_at, last_seen_at = last_acquisition_at")


def downgrade() -> None:
    for name in (
        "latency_ms_avg",
        "total_packets_lost",
        "total_events_quarantined",
        "total_events_duplicate",
        "last_error",
        "last_failure_at",
        "last_success_at",
        "last_seen_at",
    ):
        op.drop_column("data_sources", name)
