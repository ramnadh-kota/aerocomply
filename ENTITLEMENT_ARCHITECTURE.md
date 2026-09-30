# Kota Aerospace — Entitlement Architecture (as implemented)

## 1. One resolver, no cache

`entitlement_service.resolve_entitlements(db, organization_id)` is the only place commercial
entitlement is computed. It is evaluated **on every guarded request** from the database. Nothing is
cached and the JWT carries identity and roles only — so a revoked feature, a cancelled or expired
subscription, or a plan change takes effect on the caller's *next request* even with a token issued
earlier (`test_m20_commercial_entitlement_lifecycle::test_stale_token_…`). An organization suspension
is a 401 (`get_current_user` re-checks the organization every request).

```text
Organization status (SUSPENDED / deletion-requested → denied)
  → current subscriptions (TRIALING | ACTIVE | PAST_DUE, in [starts_at, ends_at))
      one per suite; two current subscriptions in the SAME suite = AMBIGUOUS (denied, fail-closed)
  → Plan → Suite → modules / pages
  → plan features (per subscribed suite)
  → tenant overrides (unexpired, inside the suite boundary)
  → usage limits (plan limit, replaced by tenant limit)
  → EntitlementResolution { resolution_status, suite_*, plan_*, modules, pages,
                            effective_features, usage_limits, active_suites }
```

`resolution_status`: ACTIVE, INACTIVE_PLAN (plan retired but the subscription still runs), SUSPENDED,
NO_SUBSCRIPTION, AMBIGUOUS, INVALID. Only ACTIVE and INACTIVE_PLAN grant anything.
PAST_DUE grants (payment grace, existing rule); CANCELED and SCHEDULED never do; EXPIRED is implicit
(`ends_at` passed → NO_SUBSCRIPTION) — there is no EXPIRED or SUSPENDED *subscription* state.

## 2. The decision: `is_feature_enabled` semantics

Used identically by REST (`require_feature`) and LISA tools (`_require_entitlement`):
1. resolution not granting → **deny**
2. the key configured anywhere (plan row or override, any spelling/alias) → the configured value (any `true` wins)
3. configured nowhere → **deny**, except **baseline features** `audit_logging` and `release_readiness`
   (`DEFAULT_ON_FEATURES`), which no seeded plan lists but every tenant has always had; they are on unless a plan row or override
   explicitly disables them. The frontend mirrors this (`DEFAULT_ON_FEATURES` in `featureKeys.ts`).

## 3. Suite boundary (defence in depth)

- A plan belongs to exactly one suite; `UNIQUE(suite_id, code)`.
- Writing a plan feature outside its suite's domain is rejected (`feature_outside_suite_boundary`); so is a tenant override outside the organization's suite.
- A subscription may not be moved to another suite's plan (`suite_plan_mismatch`); a plan with subscribers may not change suite.
- **Known gap**: pre-existing rows are not re-validated on read, and the legacy `register-organization`
  default plan mixes drone and aircraft features under DRONE_UAV; enforcing the boundary on read would break it.
  `KOTA_PRODUCTION_DATA_READINESS.md` contains the SQL to find such rows in production.

## 4. Enforcement points and error codes

| Layer | Mechanism | On denial |
|---|---|---|
| REST | `Depends(require_feature(key))` (router-wide or per route) | 403 `SUITE_ENTITLEMENT_REQUIRED` when the feature is outside the organization's suite, else 403 `forbidden` |
| REST (suite) | `require_suite(...)` | 403 `SUITE_ENTITLEMENT_REQUIRED` (defined; routes use feature keys instead) |
| LISA | `execute_tool` → `_require_entitlement` (per-tool suite + feature) | `ForbiddenError` |
| Limits | `limit_enforcement_service` (`max_assets`, `max_users`, `monthly_work_orders`, `storage_gb`) | 403 `usage_limit_exceeded` |
| Webhook | DJI webhook checks the *target* tenant's `flight_telemetry` | 403 |
| Frontend | `EntitlementContext` (re-fetched on tab focus, ≤ every 15 s), sidebar (`isNavItemUnavailable`: **strict**, greys any item whose feature the organization does not have — same rule as the route guard and the backend; the older lenient `isNavItemEntitlementGated` remains only as a tested helper), `RouteEntitlementGuard` (blocks direct URLs in `NAV_FEATURE_MAP`; also hides sample-data-only pages from live sessions) | in-page "Feature Not Included" card |

Frontend behaviour is display only; a hidden or blocked page is never the authorization.

## 5. Gated surfaces (feature → backend routes)

`work_order_management` work orders/TAT · `aircraft_fleet_management` aircraft · `drone_fleet_management` drones/missions ·
`battery_analytics` batteries · `flight_telemetry` `/telemetry/*` (JWT routes), DJI webhook target, **all `/data-sources`** ·
`hums` `/hums/*` · `predictive_maintenance` HUMS prognostics (RUL) · `digital_twin` · `mro_intelligence` · `lisa_ai_copilot` ·
`helicopter_fleet_management` `/helicopters/*` · `evtol_fleet_management` `/evtols/*` (both: `battery_analytics` for eVTOL batteries) ·
`procurement_management` procurement requests, **parts, vendors, vendor availability, purchase orders, receiving, inventory, part requirements, warehouses** ·
`compliance_management` **`/compliance/*`, regulatory documents**, applicability · `advanced_compliance_intelligence` **`/assessments/*`** ·
`inspections_management` · `audit_logging` `/tenant/audit` (baseline) · `release_readiness` (baseline) · `/fleet/components` (any fleet-family feature) ·
generic `POST /assets` (the asset family's fleet feature).
**Not gated on the backend** (baseline / cross-cutting by design): findings, evidence, deferred items, maintenance requirements, AOG, control center,
intelligence and proactive signals, technicians, facilities, tenant administration. LISA gates the same data by feature, so the REST surface is
intentionally slightly more permissive for these read-mostly, tenant-scoped views.

## 6. Overrides and audit

`TenantFeatureOverride` / `TenantUsageLimit`: tenant-scoped, optional expiry, expansions need `PLATFORM_MANAGE`-level approval rules,
every create/update/remove writes an audit event **with previous values** (`platform.tenant_feature_override.*`, `platform.tenant_usage_limit.*`,
`platform.subscription.updated` with `previous_plan_id`, …).

## 7. Multi-suite organizations

An organization may hold one current subscription per suite (e.g. Drone Professional + Aircraft Enterprise). Their features aggregate;
cancelling one closes only that suite's capabilities (`test_customer_journeys_commercial::test_multi_suite_…`).
Concurrent creation of two current subscriptions for one organization/suite is serialised by a row lock and rejected (`test_concurrency`).
Such an organization reports `suite_code = MULTI_SUITE`; suite checks (`require_suite`, LISA tools) match against the suites it actually holds
(`active_suites`), not against that label. A tool or route may list several features (`require_any_feature`, comma-separated tool features):
any one entitles it.

## 8. Payment state and entitlement
TRIALING, ACTIVE and PAST_DUE (payment grace, default 14 days, clock = `subscriptions.past_due_since`) grant access; CANCELED, expired and
absent subscriptions do not. Grace expiry can cancel automatically (opt-in `BILLING_ENFORCE_GRACE`); see BILLING_ARCHITECTURE.md.
