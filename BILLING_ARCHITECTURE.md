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

## Payment failure, grace period and consequences (migration 0069)
* A failed payment moves an ACTIVE/TRIALING subscription to **PAST_DUE** and records `subscriptions.past_due_since`
  (set on the transition, cleared on recovery or end). PAST_DUE **keeps access** during the grace period
  (`DEFAULT_GRACE_DAYS` = 14). A successful payment returns it to ACTIVE and clears the clock.
* The grace clock runs from `past_due_since`, not `updated_at` (which any unrelated edit resets) — tested.
* `evaluate_dunning` reports subscriptions past grace (unpaid amount, days). `enforce_grace_expiry(execute=True)`
  **cancels** them (entitlements revoked; the organization keeps its login and its data, like any expired customer),
  marks their open invoices `UNCOLLECTIBLE`, and writes `billing.grace_expired`. Reversible: a new subscription restores
  access. Idempotent; a subscription that recovered meanwhile is skipped.
* The daily `billing.dunning` job (`python -m app.worker --schedule`) always reports; it executes only when
  `BILLING_ENFORCE_GRACE=true` (default off).
* Entitlement consequences of every state are resolved live by the entitlement resolver (ACTIVE/TRIALING/PAST_DUE grant;
  CANCELED/expired/none do not).

## Not implemented / external
* Real provider (Stripe/Razorpay/etc.), provider webhooks, tax/GST, PDF invoices, emailing invoices/dunning notices:
  NOT IMPLEMENTED (provider items need credentials: EXTERNAL_ONLY; tax/PDF/email are software but out of the current scope).
* Live payment, refund and reconciliation with a provider: EXTERNAL VALIDATION REQUIRED.
