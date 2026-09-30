# Kota Aerospace — Suite Architecture (as implemented)

```text
ProductSuite ──1:N──> Plan ──1:N──> Subscription ──N:1──> Organization
    │                   │
    ├─ ProductModule ── ProductPage / ProductFeature
    └─ (code, name, icon, is_active, display_order)
```

## Suites

Seeded by migration 0061 with stable machine codes (never display names):

| Code | Name |
|---|---|
| `DRONE_UAV` | Drone / UAV Suite |
| `AIRCRAFT` | Aircraft Suite |
| `HELICOPTER` | Helicopter Suite |
| `EVTOL_AAM` | eVTOL / AAM Suite |

More suites can be created through the platform product-catalog API without frontend changes (the frontend reads suites, plans and
navigation from the backend). The domain boundary rules (`_SUITE_DISALLOWED_FEATURES`, prefix rules in `is_feature_allowed_for_suite`)
are currently code, not data — adding a suite with a new domain needs a code change there.

## Rules (each enforced in service code and covered by tests)

| Rule | Where | Tests |
|---|---|---|
| A plan belongs to exactly one suite (`plans.suite_id NOT NULL`, `UNIQUE(suite_id, code)`); same plan code in two suites is allowed | migration 0061, `plan_service` | `test_suite_plan_subscription_architecture`, `test_phase_a_…` |
| Subscription suite = plan suite (`suite_plan_mismatch`); moving a subscription to another suite's plan is refused | `subscription_service` | `test_m20_commercial_entitlement_lifecycle` |
| One current subscription per (organization, suite); different suites coexist | `subscription_service._assert_no_ambiguity` (+ per-organization row lock) | `test_phase_a_…`, `test_concurrency` |
| A plan cannot hold features of another suite's domain; a plan with subscribers cannot change suite | `plan_service` | `test_m20_route_gating`, `test_update_plan_suite_move_guards` |
| Overrides cannot cross the suite boundary | `tenant_entitlement_admin_service` | `test_suite_plan_subscription_architecture` |
| Provisioning is atomic and refuses a plan outside the selected suite | `provisioning_service` | `test_provisioning`, `test_provisioning_suite_mismatch_leaves_nothing` |

## Onboarding (platform-administered)

Select suite → select a plan **of that suite** → review → create organization + subscription + initial admin in one transaction
(`provision_organization`, rolled back on any failure) → admin receives an onboarding OTP email (sent after commit; failure does not undo the account).
Organization-side self-service change of suite/plan does not exist by design: the Platform Admin controls assignment.

## What each suite actually delivers today (domain coverage)

The earlier version of this document listed target markets and capabilities per suite. Measured against the code:

| Suite | Commercial architecture | Domain functionality in the codebase |
|---|---|---|
| `AIRCRAFT` | complete | **Implemented**: aircraft registry, work orders/tasks, inspections, evidence, compliance/applicability, deferred items, AOG, procurement, release readiness, TAT, LISA tools. |
| `DRONE_UAV` | complete | **Implemented**: drones, batteries, flights/missions, telemetry acquisition (MAVLink/MQTT/CSV/JSON/DJI webhook), HUMS (features, baseline, exceedance, diagnostics, prognostics/RUL), M7 signals, LISA. |
| `HELICOPTER` | suite, plans, entitlements, boundary rules | **Scaffolding only**: the shared asset model accepts `HELICOPTER` assets through the generic `/assets` endpoints. No rotorcraft-specific engines, rotor/gearbox vibration analysis or blade tracking exist. |
| `EVTOL_AAM` | suite, plans, entitlements, boundary rules | **Scaffolding only**: `EVTOL`/`AAM` asset types exist. No distributed-propulsion or inverter-thermal monitoring exists. |

Selling a Helicopter or eVTOL plan today sells the shared platform (assets, work orders, compliance, generic HUMS/telemetry APIs that are not suite-restricted), not domain engines.

## Suite changes are unsupported

Changing an organization from one suite to another is not a supported operation; provision the new suite as an additional subscription and cancel the old one.

## Data protection at the suite boundary

Suite boundaries are enforced at the API (feature/suite dependencies), in LISA (per-tool suite and feature), and in the resolver. **Row-level data is
isolated by tenant (`organization_id`), not by suite**: a drone organization's data is unreachable because its tenant filter and entitlements exclude
aircraft routes, and `test_tenant_isolation_end_to_end` proves no tenant-to-tenant leakage across 110 id-addressed and 58 list/aggregate operations.
