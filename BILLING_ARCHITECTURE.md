# Billing Architecture

Status: **implemented and tested against a deterministic test provider only.** No real payment provider is
integrated. Any live-money claim is **EXTERNAL VALIDATION REQUIRED**.

## Layers

```
subscription_service  (Suite -> Plan -> Subscription; the entitlement source of truth)
        ^
billing_service       (prices, invoices, payments, refunds, dunning, plan change/cancel)
        ^
BillingProvider       (abstract; "test" provider today)
```

Billing never computes entitlements. It only drives subscription state through `subscription_service`
(`update_subscription` / `cancel_subscription` with `commit=False` so invoice + subscription change are one
transaction).

## Tables (migration `0064_k_billing_abstraction`)
`plan_prices` (per plan, currency, interval, amount), `invoices` (per subscription and period, unique on
(subscription, period) so double renewal cannot create two), `payments` (provider reference, status, refund link).

## State machines
* Invoice: `OPEN -> PAID | VOID`, `PAID -> REFUNDED` (via payment refund). Illegal transitions are rejected.
* Payment: `SUCCEEDED | FAILED | REFUNDED`. A failed payment leaves the invoice `OPEN` and surfaces in dunning.
* `renew` is idempotent: it returns the already-issued future invoice instead of issuing another.

## API (`app/api/v1/billing.py`)
Platform (`PLATFORM_MANAGE`): plan prices GET/PUT, issue invoice, pay, refund, change-plan, cancel, dunning list.
Tenant (own organization only): list invoices, list payments of an invoice. Tenant isolation is covered by
`test_billing_lifecycle.py` and the end-to-end isolation probe.

## Provider safety
`settings.billing_provider` defaults to `test`. In `environment == production` the test provider is **refused**
(`billing_service`), so an unconfigured production deployment fails closed rather than pretending to charge.
Adding a real provider = implement `BillingProvider`, register it, add webhook signature verification
(secrets from environment only), then run the external validation below.

## Not implemented / external
* Real provider (Stripe/Razorpay/etc.), webhooks, tax/GST, PDF invoices, emailing invoices: NOT IMPLEMENTED.
* Dunning is a read-only report of overdue open invoices; automated retries/notifications need a scheduler
  (see `PRODUCTION_RUNBOOK.md`, "Background jobs").
* Live payment, refund and reconciliation with a provider: EXTERNAL VALIDATION REQUIRED.
