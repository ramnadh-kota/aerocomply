"""Phase 18.2: platform product catalog (Suite -> Module -> Page/Feature).

Written by hand, matching 0024/0025/0026/0027's precedent (autogenerate is
currently broken on this codebase -- see those migrations' own docstrings).

Purely additive: four new, platform-global tables (no organization_id,
matching Plan/PlanFeature's existing precedent -- see 0024's docstring for
the same reasoning). No existing table is touched, no existing FK is
repointed, and nothing here is referenced by any existing table -- see
app/models/product_catalog.py's module docstring for why there is
deliberately no foreign key from plan_features.feature_key (or any other
existing commercial table) into product_features.code.

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_suites",
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
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_product_suites_code", "product_suites", ["code"])

    op.create_table(
        "product_modules",
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
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["suite_id"],
            ["product_suites.id"],
            name="fk_product_modules_suite_id_product_suites",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_product_modules_code", "product_modules", ["code"])
    op.create_index("ix_product_modules_suite_id", "product_modules", ["suite_id"])

    op.create_table(
        "product_pages",
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
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("route", sa.String(255), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["product_modules.id"],
            name="fk_product_pages_module_id_product_modules",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_product_pages_code", "product_pages", ["code"])
    op.create_index("ix_product_pages_module_id", "product_pages", ["module_id"])

    op.create_table(
        "product_features",
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
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["module_id"],
            ["product_modules.id"],
            name="fk_product_features_module_id_product_modules",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_product_features_code", "product_features", ["code"])
    op.create_index("ix_product_features_module_id", "product_features", ["module_id"])


def downgrade() -> None:
    op.drop_index("ix_product_features_module_id", table_name="product_features")
    op.drop_index("ix_product_features_code", table_name="product_features")
    op.drop_table("product_features")

    op.drop_index("ix_product_pages_module_id", table_name="product_pages")
    op.drop_index("ix_product_pages_code", table_name="product_pages")
    op.drop_table("product_pages")

    op.drop_index("ix_product_modules_suite_id", table_name="product_modules")
    op.drop_index("ix_product_modules_code", table_name="product_modules")
    op.drop_table("product_modules")

    op.drop_index("ix_product_suites_code", table_name="product_suites")
    op.drop_table("product_suites")
