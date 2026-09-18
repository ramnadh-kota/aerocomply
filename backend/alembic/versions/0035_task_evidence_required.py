"""M17.6A: add Task.evidence_required.

Release readiness (app/services/release_readiness_service.py) needs a way to
know a task requires evidence *before* any Evidence row exists for it --
today, a task with zero Evidence rows is invisible to the EVIDENCE blocker
check even if evidence was always required, because Evidence rows are only
created once a submission happens. This adds a requirement-level boolean on
Task (the actual unit of work being asked for evidence) rather than a flag
on Evidence itself, since Evidence is a per-submission record that may
legitimately not exist yet.

Backfilled to `false` for every existing task, so no pre-existing task
retroactively becomes an evidence blocker.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "evidence_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("tasks", "evidence_required", server_default=None)


def downgrade() -> None:
    op.drop_column("tasks", "evidence_required")
