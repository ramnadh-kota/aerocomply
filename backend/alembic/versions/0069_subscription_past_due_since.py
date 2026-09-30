"""0069: subscriptions.past_due_since (payment-grace clock).

Revises: 0068
Additive nullable column. Existing PAST_DUE rows are backfilled from updated_at (the best evidence available);
downgrade drops the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE subscriptions SET past_due_since = updated_at WHERE status = 'PAST_DUE'")


def downgrade() -> None:
    op.drop_column("subscriptions", "past_due_since")
