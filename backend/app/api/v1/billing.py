"""K: billing API (provider-independent).

Platform administration (PLATFORM_MANAGE): prices, invoices, payments, plan changes, dunning report.
Tenant (ORG_MANAGE): read-only view of ITS OWN invoices and payments.
No card data is accepted or stored: `payment_method_ref` is an opaque token from the provider.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session, require_permission
from app.core.permissions import Permission
from app.models.billing import Invoice, Payment, PlanPrice
from app.schemas.auth import CurrentUser
from app.services import billing_service

router = APIRouter(tags=["billing"])


class PlanPriceIn(BaseModel):
    currency: str = Field(min_length=3, max_length=3)
    billing_interval: str
    amount_minor: int = Field(ge=0)
    trial_days: int = Field(default=0, ge=0, le=365)


class InvoiceGenerateIn(BaseModel):
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    billing_interval: str | None = None
    period_start: datetime | None = None


class PayIn(BaseModel):
    payment_method_ref: str = Field(min_length=1, max_length=128)
    provider: str | None = Field(default=None, max_length=32)


class ChangePlanIn(BaseModel):
    plan_id: uuid.UUID


def _price(p: PlanPrice) -> dict[str, Any]:
    return {"id": str(p.id), "plan_id": str(p.plan_id), "currency": p.currency,
            "billing_interval": p.billing_interval, "amount_minor": p.amount_minor,
            "trial_days": p.trial_days, "is_active": p.is_active}


def _invoice(i: Invoice) -> dict[str, Any]:
    return {"id": str(i.id), "organization_id": str(i.organization_id), "subscription_id": str(i.subscription_id),
            "number": i.number, "status": i.status, "currency": i.currency, "amount_minor": i.amount_minor,
            "billing_interval": i.billing_interval, "period_start": i.period_start.isoformat(),
            "period_end": i.period_end.isoformat(), "due_at": i.due_at.isoformat(),
            "paid_at": i.paid_at.isoformat() if i.paid_at else None}


def _payment(p: Payment) -> dict[str, Any]:
    return {"id": str(p.id), "invoice_id": str(p.invoice_id), "status": p.status, "amount_minor": p.amount_minor,
            "currency": p.currency, "provider": p.provider, "failure_code": p.failure_code,
            "created_at": p.created_at.isoformat() if p.created_at else None}


# ------------------------------------------------------------------ platform administration
@router.get("/platform/plans/{plan_id}/prices")
def list_prices(plan_id: uuid.UUID, db: Session = Depends(get_db_session),
                _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> list[dict[str, Any]]:
    return [_price(p) for p in billing_service.list_plan_prices(db, plan_id=plan_id)]


@router.put("/platform/plans/{plan_id}/prices")
def set_price(plan_id: uuid.UUID, body: PlanPriceIn, db: Session = Depends(get_db_session),
              user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    return _price(billing_service.set_plan_price(
        db, actor_user_id=user.id, actor_organization_id=user.organization_id, plan_id=plan_id,
        currency=body.currency, billing_interval=body.billing_interval, amount_minor=body.amount_minor,
        trial_days=body.trial_days))


@router.post("/platform/subscriptions/{subscription_id}/invoices", status_code=201)
def generate_invoice(subscription_id: uuid.UUID, body: InvoiceGenerateIn, db: Session = Depends(get_db_session),
                     user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    return _invoice(billing_service.generate_invoice(
        db, actor_user_id=user.id, subscription_id=subscription_id, currency=body.currency,
        billing_interval=body.billing_interval, period_start=body.period_start))


@router.get("/platform/organizations/{organization_id}/invoices")
def platform_list_invoices(organization_id: uuid.UUID, limit: int = Query(100, ge=1, le=500),
                           offset: int = Query(0, ge=0), db: Session = Depends(get_db_session),
                           _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))
                           ) -> list[dict[str, Any]]:
    return [_invoice(i) for i in billing_service.list_invoices(db, organization_id=organization_id,
                                                               limit=limit, offset=offset)]


@router.post("/platform/invoices/{invoice_id}/pay")
def pay_invoice(invoice_id: uuid.UUID, body: PayIn, db: Session = Depends(get_db_session),
                user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    return _payment(billing_service.pay_invoice(
        db, actor_user_id=user.id, invoice_id=invoice_id, payment_method_ref=body.payment_method_ref,
        provider_name=body.provider))


@router.post("/platform/payments/{payment_id}/refund")
def refund_payment(payment_id: uuid.UUID, db: Session = Depends(get_db_session),
                   user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    return _payment(billing_service.refund_payment(db, actor_user_id=user.id, payment_id=payment_id))


@router.post("/platform/subscriptions/{subscription_id}/change-plan")
def change_plan(subscription_id: uuid.UUID, body: ChangePlanIn, db: Session = Depends(get_db_session),
                user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    return billing_service.change_plan(db, actor_user_id=user.id, subscription_id=subscription_id,
                                       new_plan_id=body.plan_id)


@router.post("/platform/subscriptions/{subscription_id}/cancel")
def cancel(subscription_id: uuid.UUID, db: Session = Depends(get_db_session),
           user: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    sub = billing_service.cancel_with_billing(db, actor_user_id=user.id, subscription_id=subscription_id)
    return {"id": str(sub.id), "status": sub.status}


@router.get("/platform/billing/dunning")
def dunning_report(grace_days: int = Query(billing_service.DEFAULT_GRACE_DAYS, ge=0, le=365),
                   db: Session = Depends(get_db_session),
                   _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE))) -> dict[str, Any]:
    """Report only. Suspension for non-payment stays an explicit Platform Admin action."""
    return {"grace_days": grace_days, "items": billing_service.evaluate_dunning(db, grace_days=grace_days)}


# ------------------------------------------------------------------ tenant (own data, read-only)
@router.get("/tenant/billing/invoices")
def my_invoices(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db_session),
                user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE))) -> list[dict[str, Any]]:
    return [_invoice(i) for i in billing_service.list_invoices(db, organization_id=user.organization_id,
                                                               limit=limit, offset=offset)]


@router.get("/tenant/billing/invoices/{invoice_id}/payments")
def my_invoice_payments(invoice_id: uuid.UUID, db: Session = Depends(get_db_session),
                        user: CurrentUser = Depends(require_permission(Permission.ORG_MANAGE))
                        ) -> list[dict[str, Any]]:
    # tenant-scoped inside the service: another organization's invoice is a 404
    return [_payment(p) for p in billing_service.list_payments(db, organization_id=user.organization_id,
                                                               invoice_id=invoice_id)]
