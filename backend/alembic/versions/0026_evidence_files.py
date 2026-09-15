"""M16.2: evidence_files table -- file metadata for Evidence records.

Written by hand, matching 0024/0025 (autogenerate is currently broken on
this codebase -- app/models/warehouse.py's Location model is not imported
early enough for FK metadata resolution -- unrelated and out of scope here).

Schema/metadata only: no upload/download/delete endpoint exists yet (that's
M16.4/M16.5/M16.6), and nothing writes to this table yet.

Tenant-scoping note: evidence_files.organization_id is NOT declared as a
composite FK against (evidence.id, organization_id), even though every row
must in fact satisfy evidence_files.organization_id == evidence.organization_id
for a matching evidence_id. Two reasons, both matching existing precedent in
this codebase rather than inventing a new pattern for this one table:
  1. TenantScopedMixin's organization_id is not a foreign key anywhere in
     this schema (see app/db/base.py and BL-01c in docs/FULL_SYSTEM_AUDIT.md)
     -- tenant scoping across this entire codebase is an application-layer
     invariant, not a database-enforced one.
  2. Enforcing it via a composite FK would require adding a UNIQUE
     constraint on (evidence.id, organization_id) to the existing `evidence`
     table purely to support this one child table's FK target -- a bigger,
     unrelated schema change to a table this migration should not otherwise
     touch.
This is a deliberate scope boundary, not an oversight: M16.3's service layer
is responsible for verifying evidence_files.organization_id ==
evidence.organization_id before ever writing a row (re-deriving
organization_id from the authenticated caller and the looked-up Evidence
row, exactly like every other tenant-scoped service function in this
codebase already does), and a regression test for that lives in M16.3, not
here.

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-15

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_files",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_evidence_files_evidence_id_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_evidence_files_uploaded_by_user_id_users",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0", name="ck_evidence_files_size_bytes_non_negative"
        ),
        sa.UniqueConstraint("storage_key", name="uq_evidence_files_storage_key"),
    )
    op.create_index(
        "ix_evidence_files_organization_id", "evidence_files", ["organization_id"]
    )
    op.create_index("ix_evidence_files_evidence_id", "evidence_files", ["evidence_id"])
    op.create_index("ix_evidence_files_status", "evidence_files", ["status"])
    op.create_index(
        "ix_evidence_files_organization_id_status",
        "evidence_files",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("evidence_files")
