"""K: billing lifecycle. The provider is the deterministic TEST double: no money moves and nothing
here validates a real payment provider (see BILLING_ARCHITECTURE.md)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import ConflictError
from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.billing import Invoice, Payment
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription
from app.models.user import User, UserRole
from app.services import billing_service as bs
from app.services.entitlement_service import resolve_entitlements

PW = "TestPassword123!"


def _suite(db, code):
    return db.execute(select(ProductSuite).where(ProductSuite.code == code)).scalar_one()


def _plan(db, suite_code="DRONE_UAV", name="Pro"):
    p = Plan(suite_id=_suite(db, suite_code).id, code=f"B-{uuid.uuid4().hex[:8]}", name=name, is_active=True)
    db.add(p)
    db.flush()
    return p


def _org(db, name="Bill Org"):
    o = Organization(name=f"{name} {uuid.uuid4().hex[:6]}")
    db.add(o)
    db.flush()
    return o


def _price(db, plan, org, amount=99_00, cur="INR", interval="MONTHLY", trial=0):
    return bs.set_plan_price(db, actor_user_id=None, actor_organization_id=org.id, plan_id=plan.id,
                             currency=cur, billing_interval=interval, amount_minor=amount, trial_days=trial)


def _events(db, org, prefix):
    return db.scalars(select(AuditEvent.action).where(
        AuditEvent.organization_id == org.id, AuditEvent.action.like(prefix + "%"))).all()


# ------------------------------------------------------------------ prices
def test_prices_are_integers_unique_and_audited(db_session):
    org, plan = _org(db_session), None
    plan = _plan(db_session)
    p = _price(db_session, plan, org, 12_345)
    assert p.amount_minor == 12_345 and p.currency == "INR"
    again = _price(db_session, plan, org, 15_000)                    # upsert, same row
    assert again.id == p.id and again.amount_minor == 15_000
    # (rows of one test transaction share now(), so select by content, not by time)
    audits = db_session.execute(select(AuditEvent).where(AuditEvent.action == "billing.price_set",
                                                         AuditEvent.entity_id == p.id)).scalars().all()
    assert len(audits) == 2
    assert [a.event_metadata["previous"]["amount_minor"] for a in audits if a.event_metadata["previous"]] == [12_345]
    for bad in (dict(currency="RS", billing_interval="MONTHLY", amount_minor=1),
                dict(currency="INR", billing_interval="WEEKLY", amount_minor=1),
                dict(currency="INR", billing_interval="MONTHLY", amount_minor=-1)):
        with pytest.raises(ConflictError):
            bs.set_plan_price(db_session, actor_user_id=None, actor_organization_id=org.id, plan_id=plan.id, **bad)


def test_database_rejects_negative_or_malformed_prices(db_session):
    from app.models.billing import PlanPrice

    plan = _plan(db_session)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(PlanPrice(plan_id=plan.id, currency="INR", billing_interval="MONTHLY", amount_minor=-5))
            db_session.flush()


# ------------------------------------------------------------------ start / trial / activation
def test_paid_start_issues_first_invoice_and_payment_activates_and_extends(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    sub, invoice = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                      plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    assert sub.status == "ACTIVE" and invoice.status == "OPEN" and invoice.amount_minor == 99_00
    assert invoice.period_end > invoice.period_start and sub.suite_id == plan.suite_id

    pay = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_ok")
    assert pay.status == "SUCCEEDED"
    db_session.refresh(invoice); db_session.refresh(sub)
    assert invoice.status == "PAID" and invoice.paid_at is not None
    assert sub.status == "ACTIVE" and sub.ends_at >= invoice.period_end
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "ACTIVE"
    assert set(_events(db_session, org, "billing.")) >= {"billing.invoice_generated", "billing.payment_succeeded"}


def test_trial_starts_trialing_without_invoice_then_first_invoice_activates(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org, trial=14)
    sub, invoice = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                      plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    assert sub.status == "TRIALING" and invoice is None
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "ACTIVE"   # trial grants access
    assert (sub.ends_at - sub.starts_at).days == 14
    inv = bs.generate_invoice(db_session, actor_user_id=None, subscription_id=sub.id, currency="INR",
                              billing_interval="MONTHLY", period_start=sub.ends_at)
    bs.pay_invoice(db_session, actor_user_id=None, invoice_id=inv.id, payment_method_ref="pm_test_ok")
    db_session.refresh(sub)
    assert sub.status == "ACTIVE" and sub.ends_at >= inv.period_end


def test_start_without_a_defined_price_is_refused(db_session):
    org, plan = _org(db_session), _plan(db_session)
    with pytest.raises(ConflictError) as e:
        bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                           plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    assert e.value.code == "price_not_defined"


# ------------------------------------------------------------------ failure / recovery
def test_failed_payment_makes_past_due_keeps_grace_access_and_success_recovers(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    sub, invoice = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                      plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    bad = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_decline")
    assert bad.status == "FAILED" and bad.failure_code == "card_declined"
    db_session.refresh(sub); db_session.refresh(invoice)
    assert sub.status == "PAST_DUE" and invoice.status == "OPEN"
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "ACTIVE"   # grace: access continues
    ok = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_ok")
    db_session.refresh(sub); db_session.refresh(invoice)
    assert ok.status == "SUCCEEDED" and sub.status == "ACTIVE" and invoice.status == "PAID"


def test_pending_payment_changes_nothing_yet(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    sub, invoice = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                      plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    p = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_pending")
    db_session.refresh(invoice); db_session.refresh(sub)
    assert p.status == "PENDING" and invoice.status == "OPEN" and sub.status == "ACTIVE"


def test_paying_twice_or_a_paid_invoice_is_refused_and_retrying_is_not_a_second_charge(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    _, invoice = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                    plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    a = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_decline")
    b = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_decline")
    assert a.id == b.id                                             # same attempt = same payment row
    assert db_session.scalar(select(func.count(Payment.id)).where(Payment.invoice_id == invoice.id)) == 1
    bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_ok")
    with pytest.raises(ConflictError) as e:
        bs.pay_invoice(db_session, actor_user_id=None, invoice_id=invoice.id, payment_method_ref="pm_test_ok")
    assert e.value.code == "invoice_not_open"


# ------------------------------------------------------------------ renewal / idempotency
def test_renewal_continues_the_period_and_is_idempotent(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org, interval="ANNUAL", amount=120_000_00)
    sub, first = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                    plan_id=plan.id, currency="INR", billing_interval="ANNUAL")
    bs.pay_invoice(db_session, actor_user_id=None, invoice_id=first.id, payment_method_ref="pm_test_ok")
    nxt = bs.renew(db_session, actor_user_id=None, subscription_id=sub.id)
    assert nxt.period_start == first.period_end and nxt.billing_interval == "ANNUAL" and nxt.amount_minor == 120_000_00
    assert bs.renew(db_session, actor_user_id=None, subscription_id=sub.id).id == nxt.id     # not a second invoice
    assert db_session.scalar(select(func.count(Invoice.id)).where(Invoice.subscription_id == sub.id)) == 2
    assert (nxt.period_end - nxt.period_start).days in (365, 366)


def test_database_prevents_two_invoices_for_one_period(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    sub, invoice = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                      plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    dup = Invoice(organization_id=org.id, subscription_id=sub.id, plan_id=plan.id, number=f"X-{uuid.uuid4().hex}",
                  currency="INR", amount_minor=1, status="OPEN", billing_interval="MONTHLY",
                  period_start=invoice.period_start, period_end=invoice.period_end, due_at=invoice.due_at)
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(dup)
            db_session.flush()


def test_month_arithmetic_clamps_end_of_month():
    assert bs._add_months(datetime(2026, 1, 31, tzinfo=UTC), 1) == datetime(2026, 2, 28, tzinfo=UTC)
    assert bs._add_months(datetime(2028, 1, 31, tzinfo=UTC), 1) == datetime(2028, 2, 29, tzinfo=UTC)
    assert bs._add_months(datetime(2026, 11, 15, tzinfo=UTC), 3) == datetime(2027, 2, 15, tzinfo=UTC)


# ------------------------------------------------------------------ upgrade / downgrade / cancel
def test_plan_change_is_same_suite_only_and_classified_without_proration(db_session):
    org = _org(db_session)
    starter, pro = _plan(db_session, name="Starter"), _plan(db_session, name="Pro")
    other_suite = _plan(db_session, "AIRCRAFT", name="Air Pro")
    _price(db_session, starter, org, 50_00)
    _price(db_session, pro, org, 200_00)
    sub, inv = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                  plan_id=starter.id, currency="INR", billing_interval="MONTHLY")
    up = bs.change_plan(db_session, actor_user_id=None, subscription_id=sub.id, new_plan_id=pro.id)
    assert up["direction"] == "UPGRADE" and up["proration"] == "NONE" and up["new_amount_minor"] == 200_00
    db_session.refresh(sub)
    assert sub.plan_id == pro.id
    down = bs.change_plan(db_session, actor_user_id=None, subscription_id=sub.id, new_plan_id=starter.id)
    assert down["direction"] == "DOWNGRADE"
    with pytest.raises(ConflictError) as e:                               # never DRONE subscription + AIRCRAFT plan
        bs.change_plan(db_session, actor_user_id=None, subscription_id=sub.id, new_plan_id=other_suite.id)
    assert e.value.code == "suite_plan_mismatch"
    assert "billing.plan_changed" in _events(db_session, org, "billing.")


def test_cancel_voids_open_invoices_closes_access_and_is_terminal(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    sub, inv = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                  plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    bs.cancel_with_billing(db_session, actor_user_id=None, subscription_id=sub.id)
    db_session.refresh(sub); db_session.refresh(inv)
    assert sub.status == "CANCELED" and inv.status == "VOID"
    assert resolve_entitlements(db_session, organization_id=org.id).resolution_status == "NO_SUBSCRIPTION"
    with pytest.raises(ConflictError):
        bs.generate_invoice(db_session, actor_user_id=None, subscription_id=sub.id,
                            period_start=inv.period_end)


def test_refund_only_succeeded_payments_and_voids_the_invoice(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    _, inv = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    failed = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=inv.id, payment_method_ref="pm_test_decline")
    with pytest.raises(ConflictError):
        bs.refund_payment(db_session, actor_user_id=None, payment_id=failed.id)
    good = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=inv.id, payment_method_ref="pm_test_ok")
    refunded = bs.refund_payment(db_session, actor_user_id=None, payment_id=good.id)
    db_session.refresh(inv)
    assert refunded.status == "REFUNDED" and inv.status == "VOID"


def test_dunning_is_report_only(db_session):
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    sub, inv = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                  plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    bs.pay_invoice(db_session, actor_user_id=None, invoice_id=inv.id, payment_method_ref="pm_test_decline")
    assert bs.evaluate_dunning(db_session) == []                                       # inside grace
    later = datetime.now(UTC) + timedelta(days=15)
    report = bs.evaluate_dunning(db_session, now=later)
    assert [r["subscription_id"] for r in report] == [str(sub.id)]
    assert report[0]["amount_due_minor"] == 99_00 and report[0]["recommended_action"] == "REVIEW_FOR_SUSPENSION"
    db_session.refresh(sub)
    assert sub.status == "PAST_DUE"                                                    # nothing was changed


# ------------------------------------------------------------------ provider safety
def test_test_provider_is_refused_in_production(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(bs, "get_settings", lambda: SimpleNamespace(environment="production", billing_provider="test"))
    with pytest.raises(ConflictError) as e:
        bs.get_provider()
    assert e.value.code == "payment_provider_not_configured"
    monkeypatch.setattr(bs, "get_settings", lambda: SimpleNamespace(environment="staging", billing_provider="nope"))
    with pytest.raises(ConflictError):
        bs.get_provider()


def test_a_custom_provider_can_be_plugged_in_without_touching_domain_code(db_session, monkeypatch):
    calls = []

    class Recording:
        name = "recording"

        def charge(self, *, amount_minor, currency, payment_method_ref, idempotency_key):
            calls.append((amount_minor, currency, payment_method_ref))
            return bs.ProviderResult("SUCCEEDED", "rec_1")

        def refund(self, *, provider_ref, amount_minor):
            return bs.ProviderResult("REFUNDED", provider_ref + "_r")

    monkeypatch.setitem(bs._PROVIDERS, "recording", Recording())
    org, plan = _org(db_session), _plan(db_session)
    _price(db_session, plan, org)
    _, inv = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=org.id,
                                                plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    pay = bs.pay_invoice(db_session, actor_user_id=None, invoice_id=inv.id, payment_method_ref="tok_x",
                         provider_name="recording")
    assert pay.provider == "recording" and calls == [(99_00, "INR", "tok_x")]


# ------------------------------------------------------------------ HTTP: RBAC and tenant isolation
def _login(client, db, org, role):
    u = User(organization_id=org.id, email=f"b-{uuid.uuid4().hex[:8]}@example.com",
             hashed_password=hash_password(PW), full_name="B", is_active=True, email_verified=True)
    db.add(u); db.flush()
    db.add(UserRole(user_id=u.id, role_name=role, organization_id=org.id))
    db.commit()
    tok = client.post("/api/v1/auth/login", json={"email": u.email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_http_platform_flow_and_tenant_read_only_isolation(client, db_session):
    platform = _org(db_session, "Ops")
    ph = _login(client, db_session, platform, "PLATFORM_ADMIN")
    cust_a, cust_b = _org(db_session, "A"), _org(db_session, "B")
    plan = _plan(db_session)
    ah = _login(client, db_session, cust_a, "ORG_ADMIN")
    bh = _login(client, db_session, cust_b, "ORG_ADMIN")
    vh = _login(client, db_session, cust_a, "VIEWER")

    r = client.put(f"/api/v1/platform/plans/{plan.id}/prices", headers=ph,
                   json={"currency": "inr", "billing_interval": "MONTHLY", "amount_minor": 4900_00})
    assert r.status_code == 200 and r.json()["currency"] == "INR"
    sub, inv = bs.start_subscription_with_billing(db_session, actor_user_id=None, organization_id=cust_a.id,
                                                  plan_id=plan.id, currency="INR", billing_interval="MONTHLY")
    db_session.commit()

    pay = client.post(f"/api/v1/platform/invoices/{inv.id}/pay", headers=ph, json={"payment_method_ref": "pm_test_ok"})
    assert pay.status_code == 200 and pay.json()["status"] == "SUCCEEDED"
    listed = client.get(f"/api/v1/platform/organizations/{cust_a.id}/invoices", headers=ph).json()
    assert [i["status"] for i in listed] == ["PAID"]

    # tenant: sees its own invoices read-only; another tenant sees none of them
    mine = client.get("/api/v1/tenant/billing/invoices", headers=ah)
    assert mine.status_code == 200 and [i["id"] for i in mine.json()] == [str(inv.id)]
    assert client.get("/api/v1/tenant/billing/invoices", headers=bh).json() == []
    assert client.get(f"/api/v1/tenant/billing/invoices/{inv.id}/payments", headers=ah).status_code == 200
    assert client.get(f"/api/v1/tenant/billing/invoices/{inv.id}/payments", headers=bh).status_code == 404
    # RBAC: a tenant admin cannot use platform billing; a viewer cannot even read invoices
    assert client.post(f"/api/v1/platform/invoices/{inv.id}/pay", headers=ah, json={"payment_method_ref": "pm_test_ok"}).status_code == 403
    assert client.put(f"/api/v1/platform/plans/{plan.id}/prices", headers=ah,
                      json={"currency": "INR", "billing_interval": "MONTHLY", "amount_minor": 1}).status_code == 403
    assert client.get("/api/v1/tenant/billing/invoices", headers=vh).status_code == 403
    assert client.get("/api/v1/platform/billing/dunning", headers=ah).status_code == 403
    assert client.get("/api/v1/platform/billing/dunning", headers=ph).status_code == 200
    assert client.get("/api/v1/tenant/billing/invoices").status_code == 401
