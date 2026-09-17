"""Phase 18.4: Facilities Foundation -- tenant-owned physical operational
sites (hangar, workshop, warehouse, station, office, store, other), the
canonical parent for assets going forward.

Written by hand, matching prior migrations' precedent (autogenerate is
currently broken on this codebase).

Purely additive: one new tenant-scoped table (`facilities`) plus one
nullable, RESTRICT-on-delete FK column on the existing `assets` table
(`facility_id`). No existing table's other columns are touched, no
existing FK is repointed.

Deliberately NOT touching `warehouses`/`locations` (the existing
parts/inventory storage-location concept) -- see app/models/facility.py's
module docstring for why Facility is a separate, genuinely different
concept rather than a rename/extension of Warehouse.

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "facilities",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Plain column, not a real FK -- matches this codebase's repo-wide
        # TenantScopedMixin convention (tenant isolation is
        # application-layer only; see e.g. app/models/user.py, app/models/
        # subscription.py).
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("facility_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.UniqueConstraint("organization_id", "code", name="uq_facilities_organization_id_code"),
    )
    op.create_index("ix_facilities_organization_id", "facilities", ["organization_id"])
    op.create_index("ix_facilities_code", "facilities", ["code"])

    op.add_column(
        "assets",
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_assets_facility_id_facilities",
        "assets",
        "facilities",
        ["facility_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_assets_facility_id", "assets", ["facility_id"])


def downgrade() -> None:
    op.drop_index("ix_assets_facility_id", table_name="assets")
    op.drop_constraint("fk_assets_facility_id_facilities", "assets", type_="foreignkey")
    op.drop_column("assets", "facility_id")

    op.drop_index("ix_facilities_code", table_name="facilities")
    op.drop_index("ix_facilities_organization_id", table_name="facilities")
    op.drop_table("facilities")
