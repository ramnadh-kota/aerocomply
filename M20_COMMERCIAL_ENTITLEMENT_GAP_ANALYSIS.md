# M20 — Commercial Entitlement Gap Analysis

Method: traced actual code paths (not docs). Files read in full: `core/deps.py`,
`services/entitlement_service.py`, `subscription_service.py`, `provisioning_service.py`,
`limit_enforcement_service.py`, `core/feature_keys.py`, `api/v1/entitlements.py`,
FE `EntitlementContext.tsx`, `navFeatureMap.ts`, `FeatureGuard.tsx`, `SuiteGuard.tsx`.
Partially read (targeted): `plan_service.py`, `tenant_entitlement_admin_service.py`,
`platform_service.set_organization_status`, `api/v1/platform.py`, `api/v1/*` guard usage.
Not traced: billing/payment (no model exists), tenant FE pages beyond a grep.

> Note: repo root already holds unrelated `M20_1_REPORT.md`, `M20_2_REPORT.md`,
> `M20_AUDIT_AND_ROADMAP.md`, `M20_RELEASE_VERIFICATION.md` from a prior milestone
> numbered M20. They are not touched.

## A. The 20 questions — what the code actually does

1. **Suite selection** — Onboarding passes `suite_id` (optional) + `plan_id` to
   `provision_organization`; suite is derived from the plan (`plan.suite_id`). Org has no suite column of its own (`org.industry` is set to the suite code as a tag).
2. **Plan selection** — `plan_id` on provision / `create_subscription`. Plan must exist, be active (provision only), and match `suite_id` if one is supplied. If `suite_id` is omitted the check is skipped (safe, since suite comes from the plan).
3. **Subscription creation** — `subscription_service.create_subscription` (status caller-supplied, ambiguity check, audit `platform.subscription.created`), or `schedule_subscription`.
4. **Activation** — `update_subscription(status=ACTIVE)` via transition table (TRIALING/PAST_DUE/SCHEDULED → ACTIVE). Nothing auto-promotes SCHEDULED when `starts_at` arrives.
5. **Suspension** — There is **no SUSPENDED subscription status**. Suspension is org-level: `POST /platform/organizations/{id}/suspend` → `Organization.status=SUSPENDED` → resolver returns `SUSPENDED`, `get_current_user` rejects tokens (401) each request.
6. **Cancellation** — `cancel_subscription` → CANCELED (terminal), audited.
7. **Expiry** — There is **no EXPIRED status**. Expiry is implicit: `ends_at <= now` makes the row non-current, resolver returns `NO_SUBSCRIPTION`. Correct enforcement, but no explicit state or audit event.
8. **Plan change** — `update_subscription(plan_id=...)` mutates the same row in place (`suite_id` follows new plan). Contradicts the model docstring ("plan change creates a new row"), and history is lost except in the audit log.
9. **Suite change** — Same code path as 8: **no check that new plan's suite equals the subscription's current suite**. Cross-suite change is silently allowed, with no error and no override cleanup. (See GAP-1.)
10. **Platform overrides** — `TenantFeatureOverride` (org-scoped, optional `expires_at`, `reason`) and `TenantUsageLimit`. Created via `tenant_entitlement_admin_service` with audit events.
11. **Tenant-visible entitlements** — `GET /entitlements` → `resolve_entitlements` (canonical). Returns merged `effective_features`, `usage_limits`, modules, pages. It does **not** expose plan baseline vs override provenance.
12. **Usage limits** — `limit_enforcement_service` checks `max_assets` (aircraft/asset/drone creation), `max_users` (2 call sites), `monthly_work_orders`, `storage_gb` helper. Raises `UsageLimitExceededError` (`usage_limit_exceeded`). Other limit keys in plans are configuration only.
13. **Modules** — Resolver lists all active modules for the suite; **no per-module enablement**. Modules are not narrowed by features.
14. **Pages** — Same: all active suite pages returned; not narrowed by features.
15. **Backend APIs** — `require_feature` on: aircraft, applicability, digital_twin, drones, hums, lisa, missions, mro_intelligence, procurement, tat, work_orders. `require_suite` is **defined but has zero call sites in `app/api`** (`grep` verified).
16. **Frontend routes** — `FeatureGuard`/`SuiteGuard` used on exactly 3 pages (`/ai`, `/aircraft`, `/drones`). Sidebar gating via `NAV_FEATURE_MAP` (nav only, not route).
17. **Bypass prevention** — Backend dependency re-resolves entitlements from DB on every request (no cache). Good — see §B.
18. **Audit** — Reuses `record_audit_event`. Events exist for plan/subscription/override/limit mutations. **Update events store only new values, not previous values**, and subscription plan change does not record the old plan.
19. **Org state reflects admin changes** — Backend: immediately (no cache). Frontend: fetched once on mount/login; **no refetch on focus/interval/navigation**.
20. **Revocation while logged in** — Backend: next API call is denied (DB re-resolved; JWT carries no entitlement claims). Org suspension → 401. Frontend: stale until reload.

## B. What is already correct (leave alone — Rule 15)

- Resolver is a single canonical pure function; overrides constrained by suite boundary (`is_feature_allowed_for_suite`).
- No entitlement cache, no entitlement claims in JWT → no stale-token authorization.
- Provisioning is one transaction (`commit=False` throughout) with rollback + compensating cleanup; pre-flight suite/plan validation with structured `suite_plan_mismatch`.
- `create_subscription` enforces plan/suite match when `suite_id` given and derives `suite_id` from plan.
- Ambiguous-subscription rejection; lifecycle transition table; overrides suite-scoped at create time.
- Limit checks are server-side.

## C. Verified gaps (to implement)

| ID | Gap | Evidence | Severity |
|----|-----|----------|----------|
| GAP-1 | `update_subscription` permits plan change across suites (DRONE_UAV → AIRCRAFT plan) with no guard or structured error; leaves overrides from old suite in DB | `subscription_service.py:233-259` | **High** |
| GAP-2 | `schedule_subscription` does not set `Subscription.suite_id` (nullable column stays NULL) → Subscription suite ≠ Plan suite integrity violation | `subscription_service.py:335-341` | Medium |
| GAP-3 | `update_subscription` plan change doesn't check plan is active (create/provision do only in provisioning) | same | Low |
| GAP-4 | `require_feature` emits `SUITE_ENTITLEMENT_REQUIRED` only when the key contains "fleet"/"operations"; otherwise `code=None` → two competing error shapes | `deps.py:190-193` | **High** (spec §12) |
| GAP-5 | Ungated backend surfaces for commercially defined features: `flight_telemetry` (`/telemetry`), `inspections_management` (`/inspections`), `release_readiness`, `battery_analytics`, `predictive_maintenance`, `audit_logging`, `advanced_compliance_intelligence` — canonical keys exist and are in FE nav map, no backend `require_feature` | `feature_keys.py`, `api/v1/telemetry.py`, `inspections.py`, `release_readiness.py` | **High** |
| GAP-6 | `require_suite` has no call sites; suite boundary enforced only indirectly via feature keys | grep | Medium |
| GAP-7 | Audit metadata lacks previous values for subscription update, feature override update, usage limit update; no `source`/plan/suite context in override events | `subscription_service.py:248-283`, `tenant_entitlement_admin_service.py:227-243` | Medium |
| GAP-8 | Suite change / cross-suite plan change / expiry not surfaced as auditable events (expiry has no event at all) | — | Medium |
| GAP-9 | Frontend never refreshes entitlements after login (no focus/visibility refetch, no poll) → stale nav/pages after admin change | `EntitlementContext.tsx:44-46` | Medium |
| GAP-10 | Frontend `hasFeature` and resolution-failure path **fail open** (null resolution ⇒ everything visible; unknown key ⇒ true). Backend still denies, but UI contradicts backend | `EntitlementContext.tsx:50-79` | Medium |
| GAP-11 | FE route guards exist on 3 pages only; `NAV_FEATURE_MAP` entries (e.g. `/maintenance/inspections`) can be visited directly and render | grep `<FeatureGuard` | Medium |
| GAP-12 | Effective-entitlement contract lacks provenance: UI can't distinguish plan default vs override (spec §7) | `EntitlementResolution` dataclass | Medium |
| GAP-13 | Modules/pages not narrowed by effective features (spec §13/14) | resolver Step 4 | Medium — design decision required |
| GAP-14 | No explicit SUSPENDED/EXPIRED subscription status (spec §8 says "as supported"; existing model does not support them) | `SubscriptionStatus` | Info — *not* adding states (spec: no unnecessary states) |
| GAP-15 | Plan-change-in-place contradicts model docstring (history loss) | model docstring vs service | Low — document |
| GAP-16 | `SubscriptionStatus.SCHEDULED` never auto-activates at `starts_at` | resolver `_CURRENT_GRANTING_STATUSES` | Info — document |

## D. Baseline run (before any M20 change)

7 entitlement test files: **58 failed, 81 passed**. All 58 failures share one root cause:
`NotNullViolation: plans.suite_id` — legacy test fixtures build `Plan(...)` without a
`suite_id`, but the Suite→Plan hierarchy (migration 0061) made the column NOT NULL.
Production code is not implicated; the fixtures predate the hierarchy. (GAP-17)
Fixing means adding a suite to those fixtures (no assertion changes).
