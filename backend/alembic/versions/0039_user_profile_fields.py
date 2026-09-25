"""Profile Completion: Authoritative User Profile fields.

1. `users.phone_number` added as nullable String(32) for authoritative contact number.
2. `users.profile_photo_url` added as nullable Text for profile photo reference or image URI.
3. `users.pending_email` added as nullable String(320) for verified email change workflow.

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone_number", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("profile_photo_url", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("pending_email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "pending_email")
    op.drop_column("users", "profile_photo_url")
    op.drop_column("users", "phone_number")
