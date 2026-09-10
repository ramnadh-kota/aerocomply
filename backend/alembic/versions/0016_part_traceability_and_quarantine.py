"""Part traceability fields, serviceability status, quarantine quantity (M3 depth)

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-10

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parts", sa.Column("serial_number", sa.String(length=128), nullable=True))
    op.add_column("parts", sa.Column("batch_or_lot", sa.String(length=128), nullable=True))
    op.add_column("parts", sa.Column("location", sa.String(length=255), nullable=True))
    op.add_column(
        "parts",
        sa.Column(
            "serviceability_status",
            sa.String(length=32),
            nullable=False,
            server_default="SERVICEABLE",
        ),
    )
    op.add_column("parts", sa.Column("quarantine_reason", sa.Text(), nullable=True))
    op.add_column(
        "parts",
        sa.Column(
            "quantity_quarantined", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
    )
    op.create_index("ix_parts_serial_number", "parts", ["serial_number"])
    op.create_check_constraint(
        "ck_parts_quantity_quarantined_non_negative", "parts", "quantity_quarantined >= 0"
    )
    op.create_check_constraint(
        "ck_parts_quantities_within_on_hand",
        "parts",
        "quantity_reserved + quantity_quarantined <= quantity_on_hand",
    )

    op.add_column(
        "inventory_transactions",
        sa.Column("quarantined_delta", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("inventory_transactions", "quarantined_delta")

    op.drop_constraint("ck_parts_quantities_within_on_hand", "parts", type_="check")
    op.drop_constraint("ck_parts_quantity_quarantined_non_negative", "parts", type_="check")
    op.drop_index("ix_parts_serial_number", table_name="parts")
    op.drop_column("parts", "quantity_quarantined")
    op.drop_column("parts", "quarantine_reason")
    op.drop_column("parts", "serviceability_status")
    op.drop_column("parts", "location")
    op.drop_column("parts", "batch_or_lot")
    op.drop_column("parts", "serial_number")
