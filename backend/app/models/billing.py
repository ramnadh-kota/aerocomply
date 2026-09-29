"""Provider-independent billing records: plan prices, invoices, payments.

These tables hold WHAT was billed and WHAT happened to it. They never hold card data or provider
secrets, and no provider-specific column exists: `provider` / `provider_ref` are opaque strings so
any payment provider can be plugged in behind app/services/billing_service.BillingProvider.

Subscription lifecycle itself stays in `subscriptions` (TRIALING / ACTIVE / PAST_DUE / CANCELED /
SCHEDULED) -- billing drives transitions through subscription_service, it does not duplicate them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPKMixin


class BillingInterval:
    MONTHLY = "MONTHLY"
    ANNUAL = "ANNUAL"
    ALL = frozenset({MONTHLY, ANNUAL})


class InvoiceStatus:
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    PAID = "PAID"
    VOID = "VOID"
    UNCOLLECTIBLE = "UNCOLLECTIBLE"


class PaymentStatus:
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PlanPrice(UUIDPKMixin, TimestampMixin, Base):
    """Global (platform-defined) price of a plan for one currency and billing interval.
    Amounts are integers in the currency's minor unit (paise, cents): no floating point money."""

    __tablename__ = "plan_prices"
    __table_args__ = (
        UniqueConstraint("plan_id", "currency", "billing_interval", name="uq_plan_prices_plan_cur_interval"),
        CheckConstraint("amount_minor >= 0", name="ck_plan_prices_amount_nonneg"),
        CheckConstraint("trial_days >= 0", name="ck_plan_prices_trial_nonneg"),
        CheckConstraint("billing_interval IN ('MONTHLY','ANNUAL')", name="ck_plan_prices_interval"),
        CheckConstraint("length(currency) = 3", name="ck_plan_prices_currency_len"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    trial_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Invoice(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        # One invoice per subscription per period: makes generation idempotent AND race-safe.
        UniqueConstraint("subscription_id", "period_start", name="uq_invoices_subscription_period"),
        CheckConstraint("amount_minor >= 0", name="ck_invoices_amount_nonneg"),
        CheckConstraint(
            "status IN ('DRAFT','OPEN','PAID','VOID','UNCOLLECTIBLE')", name="ck_invoices_status"
        ),
        Index("ix_invoices_org_status", "organization_id", "status"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=InvoiceStatus.OPEN)
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False
    )


class Payment(UUIDPKMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_ref", name="uq_payments_provider_ref"),
        CheckConstraint("amount_minor >= 0", name="ck_payments_amount_nonneg"),
        CheckConstraint(
            "status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')", name="ck_payments_status"
        ),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
