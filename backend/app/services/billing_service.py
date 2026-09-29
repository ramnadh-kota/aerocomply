"""K: provider-independent billing lifecycle.

  Plan --(PlanPrice: currency + interval + amount_minor + trial)--> Subscription --> Invoice --> Payment

Scope and honesty:
  * REAL: the data model, the invoice/payment state machine, idempotent invoice generation, the
    coupling to the existing subscription lifecycle (subscription_service does every status change,
    so suite/plan binding, transition rules and audit stay in ONE place), and tenant scoping.
  * TEST ONLY: `TestBillingProvider` is a deterministic in-process double. No money moves.
  * NOT DONE (external): a real payment provider. Implement `BillingProvider`, call
    `register_provider(...)`, set BILLING_PROVIDER. Until then payment collection is
    "EXTERNAL VALIDATION REQUIRED"; the test provider is REFUSED in production.

Lifecycle mapping (no new subscription states):
  start with trial      -> TRIALING (ends_at = trial end); first invoice is generated when the trial ends
  invoice paid          -> subscription ACTIVE, ends_at extended to the paid period end
  payment fails         -> subscription PAST_DUE (existing grace rule: access continues, see M2)
  cancel                -> CANCELED (terminal); OPEN invoices are voided
  upgrade / downgrade   -> same-suite plan change effective immediately, NO proration (documented)
  non-payment           -> `evaluate_dunning` only REPORTS subscriptions past grace; suspension is a
                           deliberate Platform Admin action (organization suspend), never automatic
"""

from __future__ import annotations

import calendar
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.models.billing import (
    BillingInterval,
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    PlanPrice,
)
from app.models.plan import Plan
from app.models.subscription import Subscription, SubscriptionStatus
from app.services import subscription_service
from app.services.audit_service import record_audit_event

log = structlog.get_logger(__name__)

DEFAULT_GRACE_DAYS = 14


# ----------------------------------------------------------------------------- providers
@dataclass(frozen=True)
class ProviderResult:
    status: str  # PENDING | SUCCEEDED | FAILED
    provider_ref: str | None = None
    failure_code: str | None = None


class BillingProvider(Protocol):
    """What a payment provider adapter must implement. Domain code never imports a provider SDK."""

    name: str

    def charge(
        self, *, amount_minor: int, currency: str, payment_method_ref: str, idempotency_key: str
    ) -> ProviderResult: ...

    def refund(self, *, provider_ref: str, amount_minor: int) -> ProviderResult: ...


class TestBillingProvider:
    """Deterministic test double. `payment_method_ref` selects the outcome:
    pm_test_ok -> SUCCEEDED, pm_test_decline -> FAILED(card_declined),
    pm_test_pending -> PENDING, anything else -> FAILED(unknown_payment_method).
    Repeating an idempotency key returns the identical result and reference."""

    __test__ = False  # not a pytest class
    name = "test"

    @staticmethod
    def _ref(idempotency_key: str) -> str:
        return "ptest_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]

    def charge(self, *, amount_minor: int, currency: str, payment_method_ref: str, idempotency_key: str) -> ProviderResult:
        ref = self._ref(idempotency_key)
        if payment_method_ref == "pm_test_ok":
            return ProviderResult(PaymentStatus.SUCCEEDED, ref)
        if payment_method_ref == "pm_test_pending":
            return ProviderResult(PaymentStatus.PENDING, ref)
        if payment_method_ref == "pm_test_decline":
            return ProviderResult(PaymentStatus.FAILED, ref, "card_declined")
        return ProviderResult(PaymentStatus.FAILED, ref, "unknown_payment_method")

    def refund(self, *, provider_ref: str, amount_minor: int) -> ProviderResult:
        return ProviderResult(PaymentStatus.REFUNDED, provider_ref + "_refund")


_PROVIDERS: dict[str, BillingProvider] = {"test": TestBillingProvider()}


def register_provider(provider: BillingProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_provider(name: str | None = None) -> BillingProvider:
    settings = get_settings()
    wanted = name or getattr(settings, "billing_provider", "test")
    if wanted == "test" and settings.environment == "production":
        raise ConflictError(
            "The test billing provider is disabled in production; no real payment provider is configured",
            code="payment_provider_not_configured",
        )
    provider = _PROVIDERS.get(wanted)
    if provider is None:
        raise ConflictError(f"Unknown billing provider {wanted!r}", code="payment_provider_not_configured")
    return provider


# ----------------------------------------------------------------------------- helpers
def _add_months(dt: datetime, months: int) -> datetime:
    """Calendar-aware month addition; the day is clamped (Jan 31 + 1 month = Feb 28/29)."""
    month_index = dt.month - 1 + months
    year, month = dt.year + month_index // 12, month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def period_end(start: datetime, interval: str) -> datetime:
    if interval == BillingInterval.MONTHLY:
        return _add_months(start, 1)
    if interval == BillingInterval.ANNUAL:
        return _add_months(start, 12)
    raise ConflictError(f"Invalid billing interval {interval!r}", code="invalid_billing_interval")


def _norm_currency(currency: str) -> str:
    cur = (currency or "").strip().upper()
    if len(cur) != 3 or not cur.isalpha():
        raise ConflictError("currency must be a 3-letter ISO code", code="invalid_currency")
    return cur


def _get_subscription(db: Session, subscription_id: uuid.UUID) -> Subscription:
    sub = db.get(Subscription, subscription_id)
    if sub is None:
        raise NotFoundError("Subscription not found")
    return sub


def _get_invoice(db: Session, invoice_id: uuid.UUID, organization_id: uuid.UUID | None = None) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if inv is None or (organization_id is not None and inv.organization_id != organization_id):
        raise NotFoundError("Invoice not found")
    return inv


def _audit(db: Session, org_id: uuid.UUID, actor: uuid.UUID | None, action: str, entity: str,
           entity_id: uuid.UUID, **meta: Any) -> None:
    record_audit_event(db, organization_id=org_id, user_id=actor, action=action,
                       entity_type=entity, entity_id=entity_id, metadata=meta)


def _finish(db: Session, commit: bool) -> None:
    db.commit() if commit else db.flush()


# ----------------------------------------------------------------------------- prices
def set_plan_price(
    db: Session, *, actor_user_id: uuid.UUID | None, actor_organization_id: uuid.UUID, plan_id: uuid.UUID,
    currency: str, billing_interval: str, amount_minor: int, trial_days: int = 0, commit: bool = True,
) -> PlanPrice:
    if db.get(Plan, plan_id) is None:
        raise NotFoundError("Plan not found")
    if billing_interval not in BillingInterval.ALL:
        raise ConflictError("billing_interval must be MONTHLY or ANNUAL", code="invalid_billing_interval")
    if amount_minor < 0 or trial_days < 0:
        raise ConflictError("amount and trial must be non-negative", code="invalid_price")
    cur = _norm_currency(currency)
    price = db.execute(
        select(PlanPrice).where(PlanPrice.plan_id == plan_id, PlanPrice.currency == cur,
                                PlanPrice.billing_interval == billing_interval)
    ).scalar_one_or_none()
    previous = None
    if price is None:
        price = PlanPrice(plan_id=plan_id, currency=cur, billing_interval=billing_interval,
                          amount_minor=amount_minor, trial_days=trial_days, is_active=True)
        db.add(price)
    else:
        previous = {"amount_minor": price.amount_minor, "trial_days": price.trial_days}
        price.amount_minor, price.trial_days, price.is_active = amount_minor, trial_days, True
    db.flush()
    _audit(db, actor_organization_id, actor_user_id, "billing.price_set", "PlanPrice", price.id,
           plan_id=str(plan_id), currency=cur, billing_interval=billing_interval,
           amount_minor=amount_minor, trial_days=trial_days, previous=previous)
    _finish(db, commit)
    return price


def list_plan_prices(db: Session, *, plan_id: uuid.UUID) -> list[PlanPrice]:
    if db.get(Plan, plan_id) is None:
        raise NotFoundError("Plan not found")
    return list(db.execute(select(PlanPrice).where(PlanPrice.plan_id == plan_id)
                           .order_by(PlanPrice.currency, PlanPrice.billing_interval)).scalars())


def _price(db: Session, plan_id: uuid.UUID, currency: str, interval: str) -> PlanPrice:
    price = db.execute(
        select(PlanPrice).where(PlanPrice.plan_id == plan_id, PlanPrice.currency == currency,
                                PlanPrice.billing_interval == interval, PlanPrice.is_active.is_(True))
    ).scalar_one_or_none()
    if price is None:
        raise ConflictError(f"No active {interval} price in {currency} is defined for this plan", code="price_not_defined")
    return price


# ----------------------------------------------------------------------------- subscription start
def start_subscription_with_billing(
    db: Session, *, actor_user_id: uuid.UUID | None, organization_id: uuid.UUID, plan_id: uuid.UUID,
    currency: str, billing_interval: str, starts_at: datetime | None = None, commit: bool = True,
) -> tuple[Subscription, Invoice | None]:
    """Create a billed subscription.

    With a trial (price.trial_days > 0): TRIALING until the trial ends, no invoice yet (issue it
    with generate_invoice/renew when the trial ends). Without a trial: ACTIVE for the first period
    with its first invoice issued OPEN immediately; if that invoice is not collected, the failed
    payment moves the subscription to PAST_DUE (grace) like any other failed collection."""
    cur = _norm_currency(currency)
    price = _price(db, plan_id, cur, billing_interval)
    start = starts_at or datetime.now(UTC)
    if price.trial_days > 0:
        trial_end = start + timedelta(days=price.trial_days)
        sub = subscription_service.create_subscription(
            db, actor_user_id=actor_user_id, organization_id=organization_id, plan_id=plan_id,
            status=SubscriptionStatus.TRIALING, starts_at=start, ends_at=trial_end, commit=False)
        _audit(db, organization_id, actor_user_id, "billing.trial_started", "Subscription", sub.id,
               trial_days=price.trial_days, currency=cur, billing_interval=billing_interval)
        _finish(db, commit)
        return sub, None
    sub = subscription_service.create_subscription(
        db, actor_user_id=actor_user_id, organization_id=organization_id, plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE, starts_at=start, ends_at=period_end(start, billing_interval), commit=False)
    invoice = generate_invoice(db, actor_user_id=actor_user_id, subscription_id=sub.id, currency=cur,
                               billing_interval=billing_interval, period_start=start, commit=False)
    _finish(db, commit)
    return sub, invoice


# ----------------------------------------------------------------------------- invoices
def generate_invoice(
    db: Session, *, actor_user_id: uuid.UUID | None, subscription_id: uuid.UUID, currency: str | None = None,
    billing_interval: str | None = None, period_start: datetime | None = None, commit: bool = True,
) -> Invoice:
    """One invoice per (subscription, period). Calling it twice for the same period returns the
    existing invoice; concurrent calls are resolved by the database unique constraint."""
    sub = _get_subscription(db, subscription_id)
    if sub.status in (SubscriptionStatus.CANCELED,):
        raise ConflictError("Cannot invoice a canceled subscription", code="subscription_canceled")
    latest = db.execute(
        select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.period_start.desc()).limit(1)
    ).scalar_one_or_none()
    cur = _norm_currency(currency or (latest.currency if latest else ""))
    interval = billing_interval or (latest.billing_interval if latest else None)
    if interval is None:
        raise ConflictError("billing_interval is required for the first invoice", code="invalid_billing_interval")
    start = period_start or (latest.period_end if latest else sub.starts_at)

    existing = db.execute(
        select(Invoice).where(Invoice.subscription_id == sub.id, Invoice.period_start == start)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    price = _price(db, sub.plan_id, cur, interval)
    invoice = Invoice(
        organization_id=sub.organization_id, subscription_id=sub.id, plan_id=sub.plan_id,
        number=f"INV-{start:%Y%m}-{uuid.uuid4().hex[:8].upper()}", currency=cur,
        amount_minor=price.amount_minor, status=InvoiceStatus.OPEN, billing_interval=interval,
        period_start=start, period_end=period_end(start, interval), due_at=start,
    )
    try:
        with db.begin_nested():
            db.add(invoice)
            db.flush()
    except IntegrityError:
        # lost a race for the same period: the winner's row is the invoice
        return db.execute(
            select(Invoice).where(Invoice.subscription_id == sub.id, Invoice.period_start == start)
        ).scalar_one()
    _audit(db, sub.organization_id, actor_user_id, "billing.invoice_generated", "Invoice", invoice.id,
           number=invoice.number, amount_minor=invoice.amount_minor, currency=cur,
           period_start=start.isoformat(), period_end=invoice.period_end.isoformat())
    _finish(db, commit)
    return invoice


def list_invoices(db: Session, *, organization_id: uuid.UUID, limit: int = 100, offset: int = 0) -> list[Invoice]:
    return list(db.execute(
        select(Invoice).where(Invoice.organization_id == organization_id)
        .order_by(Invoice.period_start.desc()).limit(min(limit, 500)).offset(offset)
    ).scalars())


def list_payments(db: Session, *, organization_id: uuid.UUID, invoice_id: uuid.UUID) -> list[Payment]:
    _get_invoice(db, invoice_id, organization_id)
    return list(db.execute(
        select(Payment).where(Payment.organization_id == organization_id, Payment.invoice_id == invoice_id)
        .order_by(Payment.created_at)
    ).scalars())


# ----------------------------------------------------------------------------- payment
def pay_invoice(
    db: Session, *, actor_user_id: uuid.UUID | None, invoice_id: uuid.UUID, payment_method_ref: str,
    provider_name: str | None = None, commit: bool = True,
) -> Payment:
    invoice = _get_invoice(db, invoice_id)
    if invoice.status != InvoiceStatus.OPEN:
        raise ConflictError(f"Invoice is {invoice.status}; only OPEN invoices can be paid", code="invoice_not_open")
    provider = get_provider(provider_name)
    result = provider.charge(
        amount_minor=invoice.amount_minor, currency=invoice.currency,
        payment_method_ref=payment_method_ref, idempotency_key=f"{invoice.id}:{payment_method_ref}",
    )
    payment = None
    if result.provider_ref:  # the same attempt repeated is the same payment, not a second charge
        payment = db.execute(select(Payment).where(Payment.provider == provider.name,
                                                   Payment.provider_ref == result.provider_ref)).scalar_one_or_none()
    if payment is None:
        payment = Payment(organization_id=invoice.organization_id, invoice_id=invoice.id,
                          amount_minor=invoice.amount_minor, currency=invoice.currency, status=result.status,
                          provider=provider.name, provider_ref=result.provider_ref, failure_code=result.failure_code)
        db.add(payment)
        db.flush()

    sub = _get_subscription(db, invoice.subscription_id)
    if result.status == PaymentStatus.SUCCEEDED:
        invoice.status, invoice.paid_at = InvoiceStatus.PAID, datetime.now(UTC)
        db.add(invoice)
        if sub.status in (SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE, SubscriptionStatus.SCHEDULED):
            subscription_service.update_subscription(db, actor_user_id=actor_user_id, subscription_id=sub.id,
                                                     status=SubscriptionStatus.ACTIVE, commit=False)
        if sub.ends_at is None or sub.ends_at < invoice.period_end:
            subscription_service.update_subscription(db, actor_user_id=actor_user_id, subscription_id=sub.id,
                                                     ends_at=invoice.period_end, commit=False)
        action = "billing.payment_succeeded"
    elif result.status == PaymentStatus.FAILED:
        if sub.status in (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING):
            subscription_service.update_subscription(db, actor_user_id=actor_user_id, subscription_id=sub.id,
                                                     status=SubscriptionStatus.PAST_DUE, commit=False)
        action = "billing.payment_failed"
    else:
        action = "billing.payment_pending"
    _audit(db, invoice.organization_id, actor_user_id, action, "Payment", payment.id,
           invoice_id=str(invoice.id), amount_minor=invoice.amount_minor, provider=provider.name,
           failure_code=result.failure_code)
    _finish(db, commit)
    return payment


def refund_payment(db: Session, *, actor_user_id: uuid.UUID | None, payment_id: uuid.UUID,
                   commit: bool = True) -> Payment:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found")
    if payment.status != PaymentStatus.SUCCEEDED or not payment.provider_ref:
        raise ConflictError("Only a SUCCEEDED payment can be refunded", code="payment_not_refundable")
    provider = get_provider(payment.provider)
    provider.refund(provider_ref=payment.provider_ref, amount_minor=payment.amount_minor)
    payment.status = PaymentStatus.REFUNDED
    invoice = db.get(Invoice, payment.invoice_id)
    if invoice is not None:
        invoice.status = InvoiceStatus.VOID  # credited; access is NOT changed automatically
    _audit(db, payment.organization_id, actor_user_id, "billing.payment_refunded", "Payment", payment.id,
           invoice_id=str(payment.invoice_id), amount_minor=payment.amount_minor)
    _finish(db, commit)
    return payment


# ----------------------------------------------------------------------------- lifecycle
def renew(db: Session, *, actor_user_id: uuid.UUID | None, subscription_id: uuid.UUID, commit: bool = True) -> Invoice:
    """Issue the next period's invoice (continues from the previous invoice's currency/interval)."""
    sub = _get_subscription(db, subscription_id)
    latest = db.execute(
        select(Invoice).where(Invoice.subscription_id == sub.id).order_by(Invoice.period_start.desc()).limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise ConflictError("Nothing to renew: the subscription has no invoice yet", code="nothing_to_renew")
    if latest.period_start > datetime.now(UTC):
        # The next period is already invoiced. Renewal must be idempotent: a scheduler that retries
        # (or two workers that race) must never bill two periods ahead.
        return latest
    return generate_invoice(db, actor_user_id=actor_user_id, subscription_id=sub.id, commit=commit)


def change_plan(db: Session, *, actor_user_id: uuid.UUID | None, subscription_id: uuid.UUID,
                new_plan_id: uuid.UUID, commit: bool = True) -> dict[str, Any]:
    """Upgrade/downgrade within the SAME suite (subscription_service enforces that and rejects
    inactive or foreign-suite plans). Effective immediately; there is NO proration -- the new price
    applies from the next invoice. Returns the direction judged by the current billing terms."""
    sub = _get_subscription(db, subscription_id)
    old_plan_id = sub.plan_id
    latest = db.execute(select(Invoice).where(Invoice.subscription_id == sub.id)
                        .order_by(Invoice.period_start.desc()).limit(1)).scalar_one_or_none()
    old_amount = new_amount = None
    if latest is not None:
        old = db.execute(select(PlanPrice).where(PlanPrice.plan_id == old_plan_id, PlanPrice.currency == latest.currency,
                                                 PlanPrice.billing_interval == latest.billing_interval)).scalar_one_or_none()
        new = db.execute(select(PlanPrice).where(PlanPrice.plan_id == new_plan_id, PlanPrice.currency == latest.currency,
                                                 PlanPrice.billing_interval == latest.billing_interval)).scalar_one_or_none()
        old_amount = old.amount_minor if old else latest.amount_minor
        new_amount = new.amount_minor if new else None
    subscription_service.update_subscription(db, actor_user_id=actor_user_id, subscription_id=sub.id,
                                             plan_id=new_plan_id)
    if new_amount is None or old_amount is None:
        direction = "UNPRICED"
    else:
        direction = "UPGRADE" if new_amount > old_amount else "DOWNGRADE" if new_amount < old_amount else "SAME_TIER"
    _audit(db, sub.organization_id, actor_user_id, "billing.plan_changed", "Subscription", sub.id,
           direction=direction, old_plan_id=str(old_plan_id), new_plan_id=str(new_plan_id),
           old_amount_minor=old_amount, new_amount_minor=new_amount, proration="NONE")
    _finish(db, commit)
    return {"direction": direction, "old_amount_minor": old_amount, "new_amount_minor": new_amount, "proration": "NONE"}


def cancel_with_billing(db: Session, *, actor_user_id: uuid.UUID | None, subscription_id: uuid.UUID,
                        commit: bool = True) -> Subscription:
    sub = _get_subscription(db, subscription_id)
    subscription_service.cancel_subscription(db, actor_user_id=actor_user_id, subscription_id=sub.id)
    voided = 0
    for inv in db.execute(select(Invoice).where(Invoice.subscription_id == sub.id,
                                                Invoice.status == InvoiceStatus.OPEN)).scalars():
        inv.status = InvoiceStatus.VOID
        voided += 1
    _audit(db, sub.organization_id, actor_user_id, "billing.subscription_canceled", "Subscription", sub.id,
           voided_invoices=voided)
    _finish(db, commit)
    return sub


def evaluate_dunning(db: Session, *, now: datetime | None = None, grace_days: int = DEFAULT_GRACE_DAYS
                     ) -> list[dict[str, Any]]:
    """REPORT ONLY. Subscriptions that have been PAST_DUE longer than the grace period, with the
    unpaid amount. Suspending an organization for non-payment is a deliberate Platform Admin action
    (POST /platform/organizations/{id}/suspend); nothing here changes access."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=grace_days)
    rows = db.execute(select(Subscription).where(Subscription.status == SubscriptionStatus.PAST_DUE,
                                                 Subscription.updated_at <= cutoff)).scalars().all()
    out = []
    for sub in rows:
        open_invoices = db.execute(select(Invoice).where(Invoice.subscription_id == sub.id,
                                                         Invoice.status == InvoiceStatus.OPEN)).scalars().all()
        out.append({
            "subscription_id": str(sub.id), "organization_id": str(sub.organization_id),
            "past_due_since": sub.updated_at.isoformat(), "days_past_due": (now - sub.updated_at).days,
            "open_invoices": len(open_invoices), "amount_due_minor": sum(i.amount_minor for i in open_invoices),
            "recommended_action": "REVIEW_FOR_SUSPENSION",
        })
    return out
