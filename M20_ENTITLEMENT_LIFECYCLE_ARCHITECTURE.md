# M20 — Entitlement Lifecycle Architecture

## Hierarchy (unchanged, verified)
Suite → Plan (belongs to exactly one suite, `UNIQUE(suite_id, code)`) → Subscription (`suite_id == plan.suite_id`) → Organization → **Effective entitlement** → Modules / Pages / Features / Limits → RBAC.

## Single source of truth
`entitlement_service.resolve_entitlements(db, organization_id)` is the only resolver.
Order: org status (SUSPENDED / deletion-requested short-circuit) → current subscription
(TRIALING/ACTIVE/PAST_DUE inside `[starts_at, ends_at)`; >1 ⇒ AMBIGUOUS) → plan → suite →
suite modules/pages → plan features → tenant overrides (unexpired, inside suite boundary) →
plan limits overridden by `TenantUsageLimit`.
Consumers: `GET /entitlements`, `GET /platform/organizations/{id}/entitlements`,
`require_feature`, `require_suite`, `limit_enforcement_service`, provisioning verification, LISA tools.
The frontend consumes `GET /entitlements` only (`EntitlementContext`).

## Lifecycle (existing model; no states added)
| State | Source | Effective result |
|---|---|---|
| TRIALING / ACTIVE / PAST_DUE | `Subscription.status` | grants (PAST_DUE = grace, existing rule) |
| SCHEDULED | status | not yet in force → NO_SUBSCRIPTION (no auto-activation at `starts_at`; explicit `update_subscription`) |
| CANCELED | status (terminal) | NO_SUBSCRIPTION, empty feature map |
| EXPIRED | implicit: `ends_at <= now` | NO_SUBSCRIPTION |
| SUSPENDED | `Organization.status` | resolver SUSPENDED; `get_current_user` returns 401 for existing tokens |

## Plan change / suite change
- Plan change: same subscription row updated in place; `suite_id` follows plan; audit records `previous_plan_id`. History lives in audit (documented deviation from model docstring).
- **Suite change is unsupported by design**: `update_subscription` raises `ConflictError(code="suite_plan_mismatch")`. Re-provision instead. Reason: suite-scoped overrides/limits would be stranded.
- Inactive target plan rejected (`inactive_plan`).

## Session / cache behaviour
No entitlement cache. JWT carries identity/roles only. Every guarded request re-resolves from the DB, so a revoked feature, cancelled subscription or plan change takes effect on the next API call with the old token; org suspension yields 401.
Frontend: entitlements fetched at login and re-fetched on tab focus/visibility (throttled 15 s). Display only; backend is authoritative.

## Error contract
- `SUITE_ENTITLEMENT_REQUIRED` — capability outside the org's suite, or no active subscription (`require_suite`).
- `forbidden` — feature inside the suite but not enabled for the plan/override.
- `usage_limit_exceeded` — server-side limit ceiling reached.
- `suite_plan_mismatch`, `inactive_plan`, `feature_outside_suite_boundary` — admin mutations (409).

## Audit (existing `record_audit_event`)
`platform.plan.*`, `platform.subscription.{created,updated,canceled,scheduled}`,
`platform.tenant_feature_override.*`, `platform.tenant_usage_limit.*`, `platform.organization.provisioned`.
M20 added previous values (`previous_plan_id`, `previous_status`, `previous_enabled`, `previous_limit_value`, …) and feature/limit keys to update events.
