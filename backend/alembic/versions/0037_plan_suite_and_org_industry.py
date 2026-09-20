"""M21.4: link Plan -> ProductSuite (nullable), add Organization.industry.

Two small, independent, additive columns bundled in one migration since
both are part of the same M21.4 "platform control plane coherence" slice
and neither depends on data from the other:

1. `plans.suite_id` -- nullable FK -> `product_suites.id` (ON DELETE
   RESTRICT, matching every other FK in product_catalog.py/plan.py). See
   app/models/plan.py's Plan.suite_id docstring for why this is a single
   nullable FK rather than a join table.
2. `organizations.industry` -- nullable string(32) classification tag. See
   app/models/organization.py's OrganizationIndustry docstring for why this
   is a plain column, not a new lookup table.

No existing table is altered beyond adding these two nullable columns; no
backfill is performed (NULL is the correct, honest value for every
pre-existing row of both kinds).

Revision ID: 0037
Revises: 0036
Create Date: 2026-09-20

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_plans_suite_id", "plans", ["suite_id"])
    op.create_foreign_key(
        "fk_plans_suite_id_product_suites",
        "plans",
        "product_suites",
        ["suite_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "organizations",
        sa.Column("industry", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "industry")

    op.drop_constraint("fk_plans_suite_id_product_suites", "plans", type_="foreignkey")
    op.drop_index("ix_plans_suite_id", table_name="plans")
    op.drop_column("plans", "suite_id")
