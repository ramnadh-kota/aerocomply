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
| `HELICOPTER` | complete | **Implemented (2026-09-30)**: `/helicopters` API + UI gated by `helicopter_fleet_management`; asset with rotor-system / blade / engine / MTOW details (`helicopter_details`, 0068); components (rotor, transmission, engine…); flight hours & cycles; maintenance requirements and lifecycle history; HUMS starter sensors (main/tail rotor and gearbox vibration, gearbox temperature, engine torque, rotor speed) with per-sensor limits; work orders on the asset; findings, M7, LISA (`list_fleet_assets`, HUMS tools); telemetry/HUMS/MRO/compliance through the shared engines. **Not implemented**: rotorcraft-specific analytics (track & balance, gearbox condition indicators, torque-spectrum diagnostics) — they need OEM data and validated algorithms; the shared deterministic HUMS engine runs on the operator-configured sensors and limits. |
| `EVTOL_AAM` | complete | **Implemented (2026-09-30)**: `/evtols` API + UI gated by `evtol_fleet_management`; configuration / propulsor count / battery energy / HV bus / MTOW / passenger details (`evtol_details`); battery packs (`battery_analytics`), components (motor, propeller, **inverter, HV distribution**, battery…) with an eVTOL-specific configuration-slot view, hours & cycles, HUMS starter sensors (one vibration sensor per propulsor, motor/inverter/battery temperature, HV bus voltage and current); the rest as above. **Not implemented**: propulsor-efficiency, inverter thermal-margin and high-voltage insulation models. |

The generic `/assets` create endpoint requires the asset family's feature (a drone organization cannot create a
helicopter through it), and every operational sub-resource (components, batteries, maintenance, lifecycle, flights,
utilization) is scoped to the asset **type** its own route family owns (`drone_service.get_airframe`), so
`/helicopters/{drone-id}/…` is a 404.

## Suite changes are unsupported

Changing an organization from one suite to another is not a supported operation; provision the new suite as an additional subscription and cancel the old one.

## Data protection at the suite boundary

Suite boundaries are enforced at the API (feature/suite dependencies), in LISA (per-tool suite and feature), and in the resolver. **Row-level data is
isolated by tenant (`organization_id`), not by suite**: a drone organization's data is unreachable because its tenant filter and entitlements exclude
aircraft routes, and `test_tenant_isolation_end_to_end` proves no tenant-to-tenant leakage across 110 id-addressed and 58 list/aggregate operations.
