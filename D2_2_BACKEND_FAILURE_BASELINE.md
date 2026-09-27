# D2.2 Backend Failure Baseline Audit

**Date:** 2026-09-27
**Scope:** Full backend regression suite, 92 failures observed after D2.2 Pass 2 (Priority Intelligence + Decision Engine).
**Purpose:** Determine, with test evidence (not assumption), whether any of the 92 pre-existing failures are caused by D2.2, before proceeding to Pass 3.

## Executive summary

**All 92 failures are confirmed, with direct evidence, to be pre-existing and unrelated to D2.2 (Pass 1 or Pass 2).**

- **91 of 92** failures share one root cause: **newly-registered organizations are never assigned a `Subscription`/`Plan` row**, so `entitlement_service.resolve_entitlements()` returns `NO_SUBSCRIPTION` for them, and every endpoint gated by `require_feature(...)` (drones, batteries, components, flights, installations, inspection-completion-identity) returns `403 Forbidden` instead of the response the test expects. This is platform/entitlement provisioning code (`app/services/auth_service.py`, `app/services/entitlement_service.py`) — outside D1, D2.1, and D2.2 entirely.
- **1 of 92** (`test_request_and_confirm_email_verification`) is a distinct, unrelated pre-existing defect in JWT/email-verification staleness handling.
- **Zero** of the 92 reference, import, or execute any D2.2 file (`app/schemas/intelligence.py`, `app/services/intelligence/*`, `app/api/v1/intelligence.py`).
- A rigorous surgical isolation comparison (full diff removed, D2.1/D2.4 foundation code kept intact) reproduces **the exact same 92 test names**, confirmed by set comparison (`comm`), not just a matching count.

No D2.2 code was modified, no failing test was modified, skipped, or xfail'd, to reach this conclusion.

## Method

1. Ran the full backend suite with the current D2.2 Pass-2 diff present, captured all 92 failing test names and full tracebacks (`--tb=short`).
2. Parsed every one of the 92 tracebacks programmatically (not by sampling) to extract each failure's exact assertion/exception line, and classified each by that literal string match — not by filename or by assumption.
3. Traced the dominant failure signature (`assert 403 == 201` / `404` / `422`, and `KeyError: 'id'`) to its source: read `app/api/v1/drones.py`'s `require_feature("drone_fleet_management")` gate, then `app/services/entitlement_service.py::resolve_entitlements` (`NO_SUBSCRIPTION` short-circuit when no current `Subscription` row exists), then confirmed `app/services/auth_service.py::register_organization` never creates a `Subscription`/`Plan` row for a newly registered organization. This is a genuine, three-hop, code-read-confirmed root cause, not a guess.
4. Performed a **surgical isolation comparison**: backed up all 8 D2.2 files (Pass 1 + Pass 2) to a session-scratch directory, removed them from the working tree, reverted **only** the 2 D2.2-specific lines in `app/api/v1/router.py` (the `intelligence` import and `include_router(intelligence.router)` line), while explicitly preserving the pre-existing `applicability`/`aerospace_intelligence` (D2.1/D2.4) router registrations — confirmed by inspection this time, after an earlier `git checkout --` attempt over-reverted and produced a false 12-test discrepancy (documented below, in "Method correction"). Ran the full suite in this state, then restored everything and re-verified 26/26 D2.2 tests still pass.
5. Compared the two 92-name failure sets with `comm` on sorted, deduplicated files (not a positional `diff`, which is noisy under pytest's non-deterministic test ordering) — the result is an exact set match in both directions (zero tests fail only with D2.2 present; zero tests fail only without it).

### Method correction (disclosed)

My first isolation attempt used `git checkout -- app/api/v1/router.py`, which reverts the *entire* uncommitted file — not just my 2 D2.2 lines. That also stripped the pre-existing, non-D2.2 `applicability` and `aerospace_intelligence` router registrations (D2.1/D2.4 foundation work, already uncommitted in the tree before this session), which broke `test_applicability_api.py` and `test_compliance_digital_thread_api.py` (12 tests) for a reason that had nothing to do with D2.2. I caught this from the isolation diff itself (12 tests failing only-without-D2.2, which made no sense causally), corrected the method to remove *only* the 2 D2.2-specific lines, and reran. The corrected run is what's reported here.

## Root cause detail: `DRONE_FLEET_MGMT_ENTITLEMENT` (91 of 92 failures)

- **Trigger:** Any test that calls `POST /api/v1/drones` (or any other `require_feature("drone_fleet_management")`-gated endpoint) using a token from an organization created via `POST /api/v1/auth/register-organization` in the same test run.
- **Mechanism:**
  1. `register_organization` (`app/services/auth_service.py`) creates the `Organization` and its first admin `User`, but creates no `Subscription` or `Plan` row.
  2. `require_feature("drone_fleet_management")` (`app/core/deps.py`) calls `resolve_entitlements(db, organization_id=...)`.
  3. `resolve_entitlements` (`app/services/entitlement_service.py`) queries for a current `Subscription`; finding none, it returns `resolution_status=NO_SUBSCRIPTION`.
  4. `require_feature` treats `NO_SUBSCRIPTION` as not-entitled and raises `403 Forbidden`.
  5. Every downstream test assertion that expected `201`/`404`/`422` from a subsequent step instead receives `403`, and 3 tests additionally raise `KeyError: 'id'` when they try to read a field off what turned out to be a 403 error body.
- **Owning code:** `app/services/auth_service.py`, `app/services/entitlement_service.py`, `app/models/product_catalog.py`/subscription+plan tables — all pre-existing, uncommitted platform/entitlement work (matches recent commit history: "feat(platform): complete tenant provisioning lifecycle", "feat(platform): complete commercial plan governance"). None of these files were read, imported, or touched by any D2.2 service.
- **Confidence:** High — traced end-to-end through actual source code, not inferred from the error message alone.

## Root cause detail: `EMAIL_VERIFIED_STALENESS` (1 of 92 failures)

- **Test:** `test_auth_verification.py::TestEmailVerification::test_request_and_confirm_email_verification`
- **Failure:** `assert me_after["email_verified"] is False` — actual value is `True`.
- **Mechanism:** The test's own comment states it expects `email_verified` to stay stale ("baked into the JWT") until the next login/refresh; the current `/me` implementation instead reflects live DB state immediately after verification, so the assertion fails.
- **Owning code:** auth/session claim-refresh logic — unrelated to D1/D2.1/D2.2, no intelligence code path involved.
- **Confidence:** High — directly evidenced by the assertion values and the test's own inline comment.

## Classification (per the requested taxonomy)

All 92 failures classify as **A — Confirmed pre-existing / unrelated**, backed by:
- A code-read-confirmed root cause (not name-matching).
- An exact-set isolation comparison proving the same 92 tests fail identically with the entire D2.2 diff removed.

None classify as B (introduced by D2.2), C (infrastructure/environment — the DB/alembic harness itself works correctly, as proven by 1371–1471 passing tests in the same runs), D (test/fixture problem — the tests are correctly written against an entitlement flow that the provisioning code doesn't yet satisfy), E is effectively the right descriptive label for the shared root cause itself (a genuine upstream provisioning defect shared across ~14 test files), or F (no failure required further investigation — all 92 were traced to one of the two root causes above with source-level confidence).

## Full 92-failure inventory

| # | Test | File | Classification | Detail |
|---|---|---|---|---|
| 1 | `TestEmailVerification::test_request_and_confirm_email_verification` | `test_auth_verification.py` | EMAIL_VERIFIED_STALENESS | AssertionError: True is False (email_verified reflects live DB state instead of the stale JWT claim the test expects) |
| 2 | `TestBatteryUsageEvaluation::test_battery_cycles_not_due` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 3 | `TestBatteryUsageEvaluation::test_battery_cycles_due_soon_and_overdue` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 4 | `TestBatteryUsageEvaluation::test_lifetime_usage_never_reset_by_accomplishment` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 5 | `TestComponentUsageEvaluation::test_component_hours_not_due` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 6 | `TestComponentUsageEvaluation::test_component_cycles_overdue` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 7 | `TestInstallationAwareUsage::test_battery_replacement_usage_does_not_transfer` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 8 | `TestMaintenanceRBACAndTenantIsolation::test_write_requires_drone_write_permission` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 9 | `TestMaintenanceRBACAndTenantIsolation::test_viewer_can_read_battery_maintenance_due` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 10 | `TestMaintenanceRBACAndTenantIsolation::test_cross_tenant_battery_applicability_rejected` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 11 | `TestMaintenanceRBACAndTenantIsolation::test_cross_tenant_battery_maintenance_due_rejected` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 12 | `TestMaintenanceRBACAndTenantIsolation::test_cross_tenant_component_maintenance_due_rejected` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 13 | `TestValidation::test_no_applicable_requirements_returns_empty_list` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 14 | `TestValidation::test_missing_battery_returns_404` | `test_battery_component_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 15 | `TestBatteryLifecycleAPI::test_get_battery_current_state` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 16 | `TestBatteryLifecycleAPI::test_battery_history_empty_before_install` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 17 | `TestBatteryLifecycleAPI::test_battery_history_install_remove_reinstall_ordering` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 18 | `TestComponentLifecycleAPI::test_get_component_current_state` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 19 | `TestComponentLifecycleAPI::test_component_history_empty_before_install` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 20 | `TestComponentLifecycleAPI::test_component_history_install_remove_reinstall_ordering` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 21 | `TestAssetLifecycleAPI::test_asset_lifecycle_empty` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 22 | `TestAssetLifecycleAPI::test_asset_lifecycle_combines_battery_and_component_events` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 23 | `TestLifecycleTenantIsolation::test_cross_tenant_battery_get_returns_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 24 | `TestLifecycleTenantIsolation::test_cross_tenant_battery_history_returns_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 25 | `TestLifecycleTenantIsolation::test_cross_tenant_component_get_and_history_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 26 | `TestLifecycleTenantIsolation::test_cross_tenant_asset_lifecycle_history_returns_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 27 | `TestLifecycleTenantIsolation::test_no_cross_tenant_data_leaks_into_own_org_response` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 28 | `TestLifecycleRBAC::test_viewer_can_read_lifecycle` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 29 | `TestLifecycleRBAC::test_unauthorized_role_cannot_read_lifecycle` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 30 | `TestSourceOfTruthUnchangedByReads::test_get_apis_do_not_mutate_state` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 31 | `TestLifecycleValidation::test_invalid_uuid_returns_422` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 422 (setup step returned 403 before reaching validation) |
| 32 | `TestLifecycleValidation::test_missing_battery_returns_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 33 | `TestLifecycleValidation::test_missing_component_returns_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 34 | `TestLifecycleValidation::test_missing_asset_lifecycle_returns_404` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 35 | `TestLifecycleValidation::test_pagination_limit_is_clamped_and_offset_applies` | `test_drone_lifecycle_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 36 | `TestApplicability::test_link_requirement_to_drone` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 37 | `TestApplicability::test_cross_tenant_applicability_rejected` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 38 | `TestApplicability::test_write_requires_drone_write_permission` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 39 | `TestUsageBasedEvaluation::test_flight_hours_not_due` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 40 | `TestUsageBasedEvaluation::test_flight_hours_due_soon_at_90_percent` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 41 | `TestUsageBasedEvaluation::test_flight_hours_overdue_at_threshold` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 42 | `TestUsageBasedEvaluation::test_flight_cycles_evaluation` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 43 | `TestUsageBasedEvaluation::test_no_flights_yet_is_not_due` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 44 | `TestUsageBasedEvaluation::test_no_applicable_requirements_returns_empty_list` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 45 | `TestAccomplishmentResetsInterval::test_accomplishment_resets_usage_baseline` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 46 | `TestTenantIsolation::test_cross_tenant_maintenance_due_returns_404` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 47 | `TestTenantIsolation::test_cross_tenant_accomplishment_rejected` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 48 | `TestTenantIsolation::test_org_b_usage_never_affects_org_a_evaluation` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 49 | `TestDeploymentReadinessRegression::test_calendar_deployment_readiness_still_works` | `test_drone_maintenance.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 50 | `TestDroneTenantIsolationAndPermissions::test_cross_tenant_cannot_attach_battery` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 51 | `TestDroneTenantIsolationAndPermissions::test_cross_tenant_cannot_record_flight` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 52 | `TestDroneTenantIsolationAndPermissions::test_cross_tenant_cannot_read_readiness` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 53 | `TestBatteryAndComponent::test_cross_tenant_cannot_attach_component` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 54 | `TestDeploymentReadiness::test_maintenance_overdue_returns_blocked` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | KeyError: 'id' (drone-creation response body was a 403 error, not a drone object) |
| 55 | `TestDeploymentReadiness::test_failed_inspection_returns_blocked` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | KeyError: 'id' (drone-creation response body was a 403 error, not a drone object) |
| 56 | `TestAudit::test_drone_and_battery_and_flight_record_audit_events` | `test_drone_operations.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 57 | `TestFlightHistoryPagination::test_flight_history_is_paginated_and_bounded` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 58 | `TestFlightHistoryPagination::test_flight_history_offset_beyond_total_returns_empty_page` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 59 | `TestFlightHistoryPagination::test_flight_history_limit_is_clamped_to_max` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 60 | `TestFlightHistoryPagination::test_flight_history_ordering_is_deterministic_newest_first` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 61 | `TestFlightHistoryPagination::test_empty_flight_history` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 62 | `TestFlightDetail::test_get_flight_by_id` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 63 | `TestFlightDetail::test_get_nonexistent_flight_returns_404` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 404 (setup step returned 403 before reaching the assertion under test) |
| 64 | `TestFlightDetail::test_get_flight_invalid_uuid_returns_422` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 422 (setup step returned 403 before reaching validation) |
| 65 | `TestFlightDetail::test_cross_tenant_flight_get_returns_404` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 66 | `TestFlightHistoryTenantIsolation::test_cross_tenant_flight_history_returns_404` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 67 | `TestFlightHistoryTenantIsolation::test_no_cross_tenant_flight_leakage_in_own_history` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 68 | `TestBatteryCycleTenantIsolation::test_recording_flight_never_increments_another_tenants_battery` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 69 | `TestBatteryCycleTenantIsolation::test_recording_flight_with_no_attached_battery_does_not_error` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 70 | `TestFlightRBAC::test_viewer_can_list_and_get_flights_but_not_record` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 71 | `TestFlightRBAC::test_unauthorized_role_cannot_read_flights` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 72 | `TestFlightValidation::test_negative_duration_rejected` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 73 | `TestFlightValidation::test_negative_cycles_rejected` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 74 | `TestFlightValidation::test_zero_duration_rejected` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 75 | `TestFlightValidation::test_invalid_pagination_offset_rejected` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 76 | `TestFlightValidation::test_invalid_pagination_limit_rejected` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 77 | `TestUtilizationRegression::test_utilization_still_correct_after_pagination_change` | `test_flight_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 78 | `test_complete_as_me_derives_inspector_from_session` | `test_inspection_completion_identity_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 79 | `test_explicit_inspector_from_other_org_rejected` | `test_inspection_completion_identity_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 80 | `test_independence_violation_still_rejected` | `test_inspection_completion_identity_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 81 | `test_independent_inspector_completion_succeeds` | `test_inspection_completion_identity_api.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 82 | `TestBatteryLifecycle::test_install_remove_reinstall_preserves_history` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 83 | `TestBatteryLifecycle::test_duplicate_active_installation_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 84 | `TestBatteryLifecycle::test_wrong_asset_removal_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 85 | `TestComponentLifecycle::test_install_remove_reinstall_preserves_history` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 86 | `TestComponentLifecycle::test_duplicate_active_installation_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 87 | `TestComponentLifecycle::test_wrong_asset_removal_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 88 | `TestCrossTenantSecurity::test_cross_tenant_installation_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 89 | `TestCrossTenantSecurity::test_cross_tenant_removal_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 90 | `TestCrossTenantSecurity::test_cross_tenant_history_access_rejected` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 91 | `TestTransactionIntegrity::test_install_records_audit_event_atomically` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |
| 92 | `TestTransactionIntegrity::test_failed_duplicate_install_leaves_state_unchanged` | `test_installation_lifecycle.py` | DRONE_FLEET_MGMT_ENTITLEMENT | AssertionError: expected 201 Created, got 403 Forbidden |

## Isolation-comparison evidence (exact-set proof)

```
With D2.2 Pass-1 + Pass-2 present:     1371 passed, 92 failed
D2.2 files + router.py's 2 lines removed
(applicability/aerospace_intelligence
 registrations explicitly preserved):  1345 passed, 92 failed   (1371 - 26 D2.2 tests = 1345)

comm -23 sorted(isolation) sorted(with-D2.2)   -> empty  (no test fails only without D2.2)
comm -13 sorted(isolation) sorted(with-D2.2)   -> empty  (no test fails only with D2.2)
```

Both failing-test-name sets are identical, element for element.

## Disposition

- **No test was modified, skipped, or xfail'd.**
- **No D1, D2.1, or unrelated application code was changed.**
- **D2.2 caused none of the 92 failures** — confirmed by source-level root-cause tracing plus an exact-set isolation comparison.
- Recommended next step (outside D2.2's scope, flagged for the platform/entitlement owner): `register_organization` should provision a default `Subscription`/`Plan` (e.g. a trial plan) for every newly created organization, or the affected tests' registration helper should do so explicitly — either fix is a platform-provisioning change, not a D2.2 change.

**Pass-3 gating conclusion: not blocked.** All 92 failures are Category A (confirmed pre-existing/unrelated); none require D2.2 rework before proceeding.
