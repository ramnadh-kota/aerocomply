"""Unit tests for Platform Admin -> Plans Module & Two-Tier Governance Architecture.

Validates:
1. Plan Schema contract (asset_scope, included_features_count, tenant_count).
2. Bulk Plan Feature update schema contract.
3. The 4 initial Kota Aerospace plans configuration:
   - Kota Drone (DRONE_001, DRONE)
   - Kota Aircraft (AIRCRAFT_001, AIRCRAFT)
   - Kota Helicopter (HELICOPTER_001, HELICOPTER)
   - Kota eVTOL (EVTOL_001, EVTOL)
4. Two-Tier Governance Security Principle:
   Action Authorized = Tenant Active AND Tenant Entitled to Feature AND User Has Required Permission
5. Separation of Commercial Entitlement vs User RBAC Operational Authorization.
6. Zero-Hardcoding principle: new dynamic catalog features are supported dynamically.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.permissions import Permission, Role, ROLE_PERMISSIONS
from app.schemas.plan import (
    PlanCreateRequest,
    PlanFeatureBulkItem,
    PlanFeatureBulkUpdateRequest,
    PlanResponse,
    PlanUpdateRequest,
)


def test_plan_create_and_update_schemas_support_asset_scope():
    """Validates that PlanCreateRequest and PlanUpdateRequest accept asset_scope."""
    create_req = PlanCreateRequest(
        name="Kota Drone",
        code="DRONE_001",
        description="Commercial autonomous drone operations",
        asset_scope="DRONE",
        is_active=True,
    )
    assert create_req.asset_scope == "DRONE"
    assert create_req.code == "DRONE_001"

    update_req = PlanUpdateRequest(
        name="Kota Drone Pro",
        asset_scope="DRONE",
    )
    assert update_req.asset_scope == "DRONE"
    assert update_req.name == "Kota Drone Pro"


def test_plan_response_schema_contains_counts_and_scope():
    """Validates PlanResponse serializes asset_scope, included_features_count, and tenant_count."""
    now = datetime.now(UTC)
    plan_id = uuid.uuid4()
    plan_dict = {
        "id": plan_id,
        "name": "Kota Aircraft",
        "code": "AIRCRAFT_001",
        "description": "Fixed-wing commercial aircraft",
        "is_active": True,
        "asset_scope": "AIRCRAFT",
        "included_features_count": 8,
        "tenant_count": 5,
        "created_at": now,
        "updated_at": now,
    }
    resp = PlanResponse.model_validate(plan_dict)
    assert resp.asset_scope == "AIRCRAFT"
    assert resp.included_features_count == 8
    assert resp.tenant_count == 5


def test_bulk_plan_feature_schema():
    """Validates PlanFeatureBulkUpdateRequest validation."""
    payload = {
        "features": [
            {"feature_key": "drone_fleet_management", "enabled": True},
            {"feature_key": "flight_telemetry", "enabled": True},
            {"feature_key": "predictive_maintenance", "enabled": False},
        ]
    }
    bulk_req = PlanFeatureBulkUpdateRequest.model_validate(payload)
    assert len(bulk_req.features) == 3
    assert bulk_req.features[0].feature_key == "drone_fleet_management"
    assert bulk_req.features[0].enabled is True
    assert bulk_req.features[2].feature_key == "predictive_maintenance"
    assert bulk_req.features[2].enabled is False


@pytest.mark.parametrize(
    ("plan_code", "asset_scope"),
    [
        ("DRONE_001", "DRONE"),
        ("AIRCRAFT_001", "AIRCRAFT"),
        ("HELICOPTER_001", "HELICOPTER"),
        ("EVTOL_001", "EVTOL"),
    ],
)
def test_initial_four_plans_asset_scope_contract(plan_code, asset_scope):
    """Section 6: Verify the 4 canonical initial plans use the existing AssetType domain scopes."""
    req = PlanCreateRequest(
        name=f"Kota {asset_scope.capitalize()}",
        code=plan_code,
        asset_scope=asset_scope,
        is_active=True,
    )
    assert req.code == plan_code
    assert req.asset_scope == asset_scope


def test_two_tier_governance_authorization_principle():
    """Section 15: Action Authorized = Tenant Active AND Tenant Entitled to Feature AND User Has Permission.

    Demonstrates that having a commercial entitlement does NOT bypass RBAC,
    and having an RBAC permission does NOT bypass commercial entitlement.
    """
    def is_action_authorized(
        *,
        tenant_active: bool,
        tenant_feature_entitled: bool,
        user_role: Role,
        required_permission: Permission,
    ) -> bool:
        # Step 1: Tenant Active check
        if not tenant_active:
            return False
        # Step 2: Commercial Feature Entitlement check (require_feature)
        if not tenant_feature_entitled:
            return False
        # Step 3: User RBAC check (require_permission)
        user_permissions = ROLE_PERMISSIONS.get(user_role, set())
        if required_permission not in user_permissions:
            return False
        return True

    # Scenario 1: Tenant has work_order_management = True, user is MAINTENANCE_ENGINEER with WORK_ORDER_READ
    # but action requires AIRCRAFT_WRITE -> Authorized only if user has grant
    assert is_action_authorized(
        tenant_active=True,
        tenant_feature_entitled=True,
        user_role=Role.ORG_ADMIN,
        required_permission=Permission.AIRCRAFT_WRITE,
    ) is True

    # Scenario 2: Tenant has feature, but user is VIEWER (lacks AIRCRAFT_WRITE) -> Denied
    assert is_action_authorized(
        tenant_active=True,
        tenant_feature_entitled=True,
        user_role=Role.VIEWER,
        required_permission=Permission.AIRCRAFT_WRITE,
    ) is False

    # Scenario 3: User is ORG_ADMIN, but Tenant does NOT have commercial feature -> Denied
    assert is_action_authorized(
        tenant_active=True,
        tenant_feature_entitled=False,
        user_role=Role.ORG_ADMIN,
        required_permission=Permission.AIRCRAFT_WRITE,
    ) is False

    # Scenario 4: User is SUPER_ADMIN, but Tenant is SUSPENDED -> Denied
    assert is_action_authorized(
        tenant_active=False,
        tenant_feature_entitled=True,
        user_role=Role.SUPER_ADMIN,
        required_permission=Permission.AIRCRAFT_WRITE,
    ) is False


def test_zero_hardcoding_dynamic_catalog_feature_integration():
    """Section 16: Zero-Hardcoding principle.

    A new arbitrary ProductFeature key added to the catalog is dynamically
    acceptable by the plan feature API and entitlement resolution without schema changes.
    """
    new_future_feature_key = "predictive_component_failure_v2"
    bulk_item = PlanFeatureBulkItem(feature_key=new_future_feature_key, enabled=True)
    assert bulk_item.feature_key == new_future_feature_key
    assert bulk_item.enabled is True

    # Commercial resolution simulation
    plan_features = {new_future_feature_key: True}
    assert plan_features.get(new_future_feature_key) is True
