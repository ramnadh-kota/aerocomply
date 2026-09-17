"""Authentication foundation: email verification + forgot/reset password OTP.

Written by hand, matching prior migrations' precedent (autogenerate is
currently broken on this codebase).

Adds:
  - users.email_verified (Boolean, default false) -- a new user starts
    unverified; register_organization's user is not auto-verified here
    (that is a service-layer decision, not a migration-time backfill
    concern) so this column simply defaults every existing row to false,
    which is truthful: no verification has ever happened for any of them.
  - auth_verification_codes: ONE shared table backing both the
    email-verification OTP flow and the forgot/reset-password OTP flow
    (a `purpose` column distinguishes them), rather than two separate
    tables -- see app/models/auth_verification.py's docstring for why a
    single table is the correct shape for "prove you currently control
    this account's email" in both cases.

Purely additive: no existing table's other columns are touched, no FK is
repointed.

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "auth_verification_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # "email_verification" | "password_reset" -- plain string, matching
        # this codebase's established convention of not using a DB enum type
        # for small closed sets (see ProductSuite/etc.'s `code` columns, and
        # EvidenceFile's status column).
        sa.Column("purpose", sa.String(32), nullable=False),
        # Never the plaintext code -- see security.hash_password (argon2),
        # reused here rather than inventing a second hashing scheme.
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_auth_verification_codes_user_purpose",
        "auth_verification_codes",
        ["user_id", "purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_verification_codes_user_purpose", table_name="auth_verification_codes")
    op.drop_table("auth_verification_codes")
    op.drop_column("users", "email_verified")
