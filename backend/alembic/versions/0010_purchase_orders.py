"""Purchase orders and lines (Milestone 3.7)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-09

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_number", sa.String(length=64), nullable=False),
        sa.Column(
            "vendor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vendors.id"),
            nullable=False,
        ),
        sa.Column(
            "aircraft_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aircraft.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_cents", sa.Integer(), nullable=True),
        sa.Column("shipping_cents", sa.Integer(), nullable=True),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("required_by", sa.Date(), nullable=True),
        sa.Column("expected_delivery", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "approved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_purchase_orders_organization_id", "purchase_orders", ["organization_id"])
    op.create_index("ix_purchase_orders_vendor_id", "purchase_orders", ["vendor_id"])
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"])

    op.create_table(
        "purchase_order_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "purchase_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("purchase_orders.id"),
            nullable=False,
        ),
        sa.Column(
            "procurement_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("procurement_requests.id"),
            nullable=True,
        ),
        sa.Column("part_number", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_price_cents", sa.Integer(), nullable=True),
        sa.Column(
            "received_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_lines_quantity_positive"),
        sa.CheckConstraint(
            "received_quantity >= 0 AND received_quantity <= quantity",
            name="ck_purchase_order_lines_received_within_quantity",
        ),
    )
    op.create_index(
        "ix_purchase_order_lines_organization_id", "purchase_order_lines", ["organization_id"]
    )
    op.create_index(
        "ix_purchase_order_lines_purchase_order_id",
        "purchase_order_lines",
        ["purchase_order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_purchase_order_lines_purchase_order_id", table_name="purchase_order_lines"
    )
    op.drop_index(
        "ix_purchase_order_lines_organization_id", table_name="purchase_order_lines"
    )
    op.drop_table("purchase_order_lines")

    op.drop_index("ix_purchase_orders_po_number", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_vendor_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_organization_id", table_name="purchase_orders")
    op.drop_table("purchase_orders")
