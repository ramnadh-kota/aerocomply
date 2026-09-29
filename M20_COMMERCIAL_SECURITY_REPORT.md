# M20 — Commercial Security Report

## Verified (tests + live run on migrated clone of dev DB)
| Attack | Result |
|---|---|
| Drone org → `GET /aircraft` | 403 `SUITE_ENTITLEMENT_REQUIRED` |
| Aircraft org → `GET /drones` | 403 `SUITE_ENTITLEMENT_REQUIRED` |
| Drone subscription → Aircraft plan (`PATCH subscription`) | 409 `suite_plan_mismatch`, row unchanged |
| Provisioning with plan ∉ selected suite | 409 `suite_plan_mismatch`, nothing persisted |
| Override enabling out-of-suite feature | rejected `feature_outside_suite_boundary` (existing) |
| Revoked feature, token issued before revoke | 403 on next call |
| Cancelled subscription, live token | 403 |
| Suspended org, live token | 401 |
| Plan-excluded feature (in suite) | 403 `forbidden` (distinct from suite code) |
| Limit exceeded | server-side `usage_limit_exceeded` at the effective (override-aware) limit |
| Direct URL to gated frontend route | blocked by `RouteEntitlementGuard` (display); API still authoritative |

## Defects found and fixed in the unstaged work
1. Cross-suite plan change allowed in `update_subscription` (now rejected).
2. `require_feature` error code chosen by substring of the feature name (now by suite boundary).
3. `schedule_subscription` left `suite_id` NULL.
4. **Migration 0061 was not round-trippable**: `try/except` around `DROP` inside a Postgres transaction aborted the transaction, and `downgrade` did not restore the 0024 shape (`uq_plans_code` + plain index), so downgrade→re-upgrade failed. Rewritten with `IF EXISTS`; downgrade restores 0024 shape. Verified: `test_asset_foundation` migration round-trip passes; upgrade of a clone of the dev DB (47 orgs) gave 0 subscriptions without suite and 0 suite/plan mismatches.
5. `/inspections` had no commercial gate (now `inspections_management`; already present in default and seed plans).
6. Audit events lacked previous values.
7. Frontend showed stale entitlements and did not deny on non-granting subscription status.

## Test-suite adjustments (documented, not weakened)
- `conftest.py`: `Plan` before_insert default suite for legacy fixtures + `grant_features` helper (fixtures predate NOT NULL `plans.suite_id` and feature gating).
- `test_suite_plan_subscription_architecture`: assertion that a cross-suite plan update *succeeds* replaced with rejection (old assertion contradicted the "never DRONE subscription + AIRCRAFT plan" rule).
- `test_entitlement_resolution::test_lisa_feature_key_has_no_special_casing`: exact-map assertion relaxed because "LISA" is a registered alias that also exposes `lisa_ai_copilot`.
- `test_plan_administration`: Core insert now passes `suite_id`.
- `test_compliance_digital_thread_api`: entitles `aircraft_fleet_management` (route was gated; fixture used stale key).
- digital_twin / h7 / hums_feature_engine: fixtures now subscribe the gated features.
- `auth_service` default registration plan gains `hums`, `digital_twin`, `mro_intelligence` (only affects newly created default plans).

## Remaining risks
- `/telemetry` (JWT routes), `release_readiness`, `battery_analytics`, `predictive_maintenance`, `audit_logging` still have no backend `require_feature`; telemetry mixes webhook/device auth, and gating release_readiness needs plan-feature seeding first (Rule 13). Needs a product decision.
- `require_suite` still unused on routes (suite boundary enforced through domain feature keys).
- Modules/pages are suite-level, not narrowed by plan features; no plan-default-vs-override provenance in the API.
- SCHEDULED subscriptions never auto-activate; no SUSPENDED/EXPIRED subscription states (org suspension / `ends_at` used).
- `test_security_hardening::test_rate_limited_response_is_safe_and_generic` failed once under concurrent load (live servers running) and passes in isolation.
- Downgrade of 0061 fails if two suites share a plan code.
