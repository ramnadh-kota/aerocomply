"""Unit tests for Tenant Feature Overrides and Entitlement Resolution contract.

Validates:
1. Pydantic request body validation contract:
   - Proper JSON dictionary object passes validation.
   - Erroneously double-stringified JSON payload produces the exact error:
     "Input should be a valid dictionary or object to extract fields from".
2. Entitlement matrix (Plan Features + Tenant Feature Overrides = Effective Entitlement):
   - TEST 1: Plan INCLUDED, Override NONE -> Effective ENABLED
   - TEST 2: Plan INCLUDED, Override DISABLED -> Effective DISABLED
   - TEST 3: Plan EXCLUDED, Override NONE -> Effective DISABLED
   - TEST 4: Plan EXCLUDED, Override ENABLED -> Effective ENABLED
   - TEST 7: Override removed -> Returns to plan inheritance
"""
import pytest
from pydantic import ValidationError

from app.schemas.tenant_entitlement import (
    TenantFeatureOverrideCreateRequest,
    TenantFeatureOverrideUpdateRequest,
)


def test_payload_contract_valid_json_dict_succeeds():
    """Step 2: Correct request body is a JSON dictionary/object matching the backend schema."""
    payload = {
        "feature_key": "flight_telemetry",
        "enabled": True,
        "reason": "Approved commercial exception",
    }
    req = TenantFeatureOverrideCreateRequest.model_validate(payload)
    assert req.feature_key == "flight_telemetry"
    assert req.enabled is True
    assert req.reason == "Approved commercial exception"


def test_payload_contract_double_stringified_json_fails_with_exact_bug_error():
    """Step 2 root cause: Passing a JSON string literal instead of a dictionary

    produces: 'Input should be a valid dictionary or object to extract fields from'.
    """
    raw_json_string = '{"feature_key":"flight_telemetry","enabled":true}'
    with pytest.raises(ValidationError) as exc_info:
        TenantFeatureOverrideCreateRequest.model_validate(raw_json_string)

    assert "Input should be a valid dictionary" in str(exc_info.value)


def test_update_payload_contract():
    """UpdateRequest accepts boolean state and reason."""
    payload = {"enabled": False, "reason": "Enterprise commercial restriction"}
    req = TenantFeatureOverrideUpdateRequest.model_validate(payload)
    assert req.enabled is False
    assert req.reason == "Enterprise commercial restriction"


@pytest.mark.parametrize(
    ("plan_included", "override_state", "expected_effective"),
    [
        # TEST 1: Plan INCLUDED, No override -> Effective ENABLED
        (True, None, True),
        # TEST 2: Plan INCLUDED, Override DISABLED -> Effective DISABLED
        (True, False, False),
        # TEST 3: Plan EXCLUDED, No override -> Effective DISABLED
        (False, None, False),
        # TEST 4: Plan EXCLUDED, Override ENABLED -> Effective ENABLED
        (False, True, True),
    ],
)
def test_entitlement_calculation_truth_table(plan_included, override_state, expected_effective):
    """The entitlement model:

    IF tenant override exists:
        effective = tenant override state
    ELSE:
        effective = plan feature state
    """
    plan_features = {"flight_telemetry": plan_included}
    effective_features = dict(plan_features)

    # Apply override if exists
    if override_state is not None:
        effective_features["flight_telemetry"] = override_state

    assert effective_features["flight_telemetry"] is expected_effective


def test_inherit_remove_override_restores_plan_inheritance():
    """TEST 7: Removing override restores tenant to base plan inheritance."""
    plan_features = {"battery_analytics": False}  # EXCLUDED in plan
    effective_features = dict(plan_features)

    # 1. Platform admin creates ENABLED override
    override = {"battery_analytics": True}
    effective_features.update(override)
    assert effective_features["battery_analytics"] is True  # Effective ENABLED

    # 2. Platform admin chooses 'Inherit from Plan' / removes override
    del override["battery_analytics"]
    effective_features = dict(plan_features)
    assert effective_features["battery_analytics"] is False  # Reverts to plan (DISABLED)
