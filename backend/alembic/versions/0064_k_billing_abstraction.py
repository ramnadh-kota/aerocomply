"""0064: K — provider-independent billing (plan prices, invoices, payments).

Revises: 0063
Create Date: 2026-09-30

Additive only: three new tables, no change to existing ones, no data migration. Existing
organizations/subscriptions are untouched and continue to work with no prices defined.

  plan_prices  global price per (plan, currency, interval); amounts in minor units (integers)
  invoices     tenant-scoped; UNIQUE(subscription_id, period_start) => idempotent, race-safe generation
  payments     tenant-scoped attempts against an invoice; provider/provider_ref are opaque strings

Downgrade drops the three tables (billing history would be lost; take a backup first).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id_and_created():
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "plan_prices",
        *_id_and_created(),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("billing_interval", sa.String(length=16), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("trial_days", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("plan_id", "currency", "billing_interval", name="uq_plan_prices_plan_cur_interval"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_plan_prices_amount_nonneg"),
        sa.CheckConstraint("trial_days >= 0", name="ck_plan_prices_trial_nonneg"),
        sa.CheckConstraint("billing_interval IN ('MONTHLY','ANNUAL')", name="ck_plan_prices_interval"),
        sa.CheckConstraint("length(currency) = 3", name="ck_plan_prices_currency_len"),
    )
    op.create_index("ix_plan_prices_plan_id", "plan_prices", ["plan_id"])

    op.create_table(
        "invoices",
        *_id_and_created(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("billing_interval", sa.String(length=16), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("number", name="uq_invoices_number"),
        sa.UniqueConstraint("subscription_id", "period_start", name="uq_invoices_subscription_period"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_invoices_amount_nonneg"),
        sa.CheckConstraint(
            "status IN ('DRAFT','OPEN','PAID','VOID','UNCOLLECTIBLE')", name="ck_invoices_status"
        ),
    )
    op.create_index("ix_invoices_organization_id", "invoices", ["organization_id"])
    op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])
    op.create_index("ix_invoices_org_status", "invoices", ["organization_id", "status"])

    op.create_table(
        "payments",
        *_id_and_created(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_ref", sa.String(length=128), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("provider", "provider_ref", name="uq_payments_provider_ref"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_payments_amount_nonneg"),
        sa.CheckConstraint(
            "status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')", name="ck_payments_status"
        ),
    )
    op.create_index("ix_payments_organization_id", "payments", ["organization_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("invoices")
    op.drop_table("plan_prices")
