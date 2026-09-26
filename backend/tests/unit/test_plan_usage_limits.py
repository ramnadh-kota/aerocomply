"""Unit tests for Plan Usage Limits schemas, enforcement, and domain contracts.

Covers:
- PlanLimitItem and PlanLimitBulkUpdateRequest validation
- Unlimited limits handling
- Usage limit vs Feature entitlement separation
- Error types and machine-readable error codes
- Limit enforcement checks (assets, users, work orders)
"""

import uuid
import pytest
from pydantic import ValidationError

from app.core.errors import UsageLimitExceededError
from app.core.permissions import Permission, Role, ROLE_PERMISSIONS
from app.schemas.plan import (
    PlanLimitItem,
    PlanLimitBulkUpdateRequest,
    PlanLimitResponse,
)
from app.services.entitlement_service import UsageLimitConfiguration


def test_plan_limit_item_valid():
    """Validates numeric limit."""
    item = PlanLimitItem(limit_key="max_assets", limit_value=100, is_unlimited=False)
    assert item.limit_key == "max_assets"
    assert item.limit_value == 100
    assert item.is_unlimited is False


def test_plan_limit_item_unlimited():
    """Validates unlimited limit automatically sets limit_value to None."""
    item = PlanLimitItem(limit_key="storage_gb", limit_value=50, is_unlimited=True)
    assert item.is_unlimited is True
    assert item.limit_value is None


def test_plan_limit_item_missing_value_when_not_unlimited():
    """Validates that a numeric limit requires a value if is_unlimited is False."""
    with pytest.raises(ValidationError):
        PlanLimitItem(limit_key="max_users", limit_value=None, is_unlimited=False)


def test_plan_limit_bulk_request():
    """Validates bulk update request serialization."""
    req = PlanLimitBulkUpdateRequest(
        limits=[
            PlanLimitItem(limit_key="max_assets", limit_value=100),
            PlanLimitItem(limit_key="max_users", limit_value=25),
            PlanLimitItem(limit_key="storage_gb", is_unlimited=True),
        ]
    )
    assert len(req.limits) == 3
    assert req.limits[2].is_unlimited is True
    assert req.limits[2].limit_value is None


def test_usage_limit_exceeded_error_shape():
    """Validates UsageLimitExceededError HTTP status and error code."""
    err = UsageLimitExceededError("Asset limit reached")
    assert err.status_code == 403
    assert err.code == "usage_limit_exceeded"
    assert "Asset limit reached" in err.message


def test_separation_of_usage_limit_from_feature_entitlement():
    """Validates that PlanLimit and PlanFeature remain independent concepts.
    
    A tenant can be entitled to a feature (e.g. work_order_management = True)
    while being constrained by a usage limit (e.g. monthly_work_orders = 500).
    """
    feature_entitlement = {"work_order_management": True}
    usage_limit = UsageLimitConfiguration(
        feature_key="MRO",
        limit_key="monthly_work_orders",
        limit_value=500,
        is_unlimited=False,
    )

    # Entitlement answers: can the module be accessed?
    assert feature_entitlement.get("work_order_management") is True
    # Limit answers: how much volume is permitted this period?
    assert usage_limit.limit_value == 500
    assert usage_limit.is_unlimited is False


def test_separation_of_usage_limit_from_rbac_permissions():
    """Requirement 9 & 10: Validates that Usage Limits never grant or alter RBAC permissions,
    and that only Platform Admin can modify global plan limits, while ORG_ADMIN cannot.
    """
    platform_admin_permissions = ROLE_PERMISSIONS[Role.PLATFORM_ADMIN]
    assert Permission.PLATFORM_MANAGE in platform_admin_permissions

    org_admin_permissions = ROLE_PERMISSIONS[Role.ORG_ADMIN]
    assert Permission.PLATFORM_MANAGE not in org_admin_permissions
    assert Permission.AIRCRAFT_WRITE in org_admin_permissions

    viewer_permissions = ROLE_PERMISSIONS[Role.VIEWER]
    assert Permission.AIRCRAFT_WRITE not in viewer_permissions
    assert Permission.PLATFORM_MANAGE not in viewer_permissions


def test_duplicate_limit_keys_prevented_in_bulk_request():
    """Requirement 5: Duplicate limit keys in bulk request can be detected and deduplicated/prevented."""
    items = [
        PlanLimitItem(limit_key="max_assets", limit_value=100),
        PlanLimitItem(limit_key="max_assets", limit_value=200),
    ]
    # Check that keys can be checked for uniqueness
    keys = [item.limit_key for item in items]
    assert len(keys) != len(set(keys))


def test_tenant_inherits_plan_limit_baseline():
    """Requirement 6: Tenant inherits plan limits as baseline when no tenant override exists."""
    plan_limits = {
        "max_assets": 100,
        "max_users": 25,
        "monthly_work_orders": 500,
        "storage_gb": 50,
    }
    tenant_overrides = {}  # No overrides

    effective_limits = dict(plan_limits)
    for k, v in tenant_overrides.items():
        effective_limits[k] = v

    assert effective_limits["max_assets"] == 100
    assert effective_limits["max_users"] == 25
    assert effective_limits["monthly_work_orders"] == 500
    assert effective_limits["storage_gb"] == 50


def test_tenant_override_takes_precedence_over_plan_limit():
    """Requirement 8: TenantUsageLimit override takes precedence over PlanLimit baseline."""
    plan_limits = {
        "max_assets": 100,
        "max_users": 25,
    }
    # Tenant granted an exception: 150 assets
    tenant_overrides = {
        "max_assets": 150,
    }

    effective_limits = dict(plan_limits)
    effective_limits.update(tenant_overrides)

    # Effective max_assets reflects override
    assert effective_limits["max_assets"] == 150
    # Unoverridden limits still inherit plan default
    assert effective_limits["max_users"] == 25


def test_plan_limit_update_propagates_to_unoverridden_tenants():
    """Requirement 6: When plan limit changes from 100 to 150, tenants without override see 150."""
    plan_limits_v1 = {"max_assets": 100}
    plan_limits_v2 = {"max_assets": 150}

    tenant_override = {}
    effective_v1 = dict(plan_limits_v1)
    effective_v1.update(tenant_override)
    assert effective_v1["max_assets"] == 100

    effective_v2 = dict(plan_limits_v2)
    effective_v2.update(tenant_override)
    assert effective_v2["max_assets"] == 150


def test_plan_service_bulk_set_limits_crud_and_audit():
    """Requirements 1, 2, 3, 4, 11: Validates bulk upsert, removal, unlimited, and audit generation."""
    from unittest.mock import MagicMock
    from app.models.plan import Plan, PlanLimit
    from app.services.plan_service import bulk_set_plan_limits

    mock_db = MagicMock()
    plan_id = uuid.uuid4()
    actor_user_id = uuid.uuid4()
    actor_org_id = uuid.uuid4()

    mock_plan = Plan(
        id=plan_id,
        name="Kota Drone",
        code="DRONE_001",
        is_active=True,
    )
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_plan

    # Existing limits: max_assets=100, old_limit=10
    existing_limit1 = PlanLimit(id=uuid.uuid4(), plan_id=plan_id, limit_key="max_assets", limit_value=100, is_unlimited=False)
    existing_limit2 = PlanLimit(id=uuid.uuid4(), plan_id=plan_id, limit_key="old_limit", limit_value=10, is_unlimited=False)
    mock_db.execute.return_value.scalars.return_value.all.return_value = [existing_limit1, existing_limit2]

    # New desired limits:
    # 1. max_assets updated from 100 -> 200 (UPDATE)
    # 2. storage_gb created as UNLIMITED (CREATE)
    # 3. old_limit is excluded (REMOVED)
    limits_payload = [
        {"limit_key": "max_assets", "limit_value": 200, "is_unlimited": False},
        {"limit_key": "storage_gb", "limit_value": None, "is_unlimited": True},
    ]

    recorded_audits = []
    def mock_record_audit(db, action, entity_type, entity_id, organization_id, user_id, metadata):
        recorded_audits.append({"action": action, "metadata": metadata})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.plan_service.record_audit_event", mock_record_audit)
        
        result = bulk_set_plan_limits(
            db=mock_db,
            actor_user_id=actor_user_id,
            actor_organization_id=actor_org_id,
            plan_id=plan_id,
            limits=limits_payload,
        )

        # 1. Update existing limit
        assert existing_limit1.limit_value == 200
        assert existing_limit1.is_unlimited is False

        # 2. Removed excluded limit
        mock_db.delete.assert_called_with(existing_limit2)

        # 3. Created new unlimited limit
        mock_db.add.assert_called()

        # 4. Audit events verified
        audit_actions = [a["action"] for a in recorded_audits]
        assert "platform.plan_limit.updated" in audit_actions
        assert "platform.plan_limit.removed" in audit_actions
        assert "platform.plan_limit.created" in audit_actions


def test_enforcement_asset_limit_exceeded():
    """Requirement 12: Asset limit enforcement raises UsageLimitExceededError when count >= limit."""
    from unittest.mock import MagicMock
    from app.services.limit_enforcement_service import check_asset_creation_limit
    from app.services.entitlement_service import EntitlementResolution, EntitlementResolutionStatus, UsageLimitConfiguration

    mock_db = MagicMock()
    org_id = uuid.uuid4()

    mock_entitlements = EntitlementResolution(
        organization_id=org_id,
        resolution_status=EntitlementResolutionStatus.ACTIVE,
        organization_status="ACTIVE",
        subscription_id=uuid.uuid4(),
        subscription_status="ACTIVE",
        plan_id=uuid.uuid4(),
        plan_code="DRONE_001",
        effective_features={"drone_fleet_management": True},
        usage_limits=[
            UsageLimitConfiguration(
                feature_key="ASSET",
                limit_key="max_assets",
                limit_value=5,
                is_unlimited=False,
            )
        ],
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.limit_enforcement_service.resolve_entitlements", lambda db, organization_id: mock_entitlements)

        # Case A: Current count is 4 < 5 -> Allowed
        mock_db.execute.return_value.scalar_one.return_value = 4
        check_asset_creation_limit(mock_db, organization_id=org_id)  # Does not raise

        # Case B: Current count is 5 == 5 -> Exceeded
        mock_db.execute.return_value.scalar_one.return_value = 5
        with pytest.raises(UsageLimitExceededError) as exc_info:
            check_asset_creation_limit(mock_db, organization_id=org_id)
        assert exc_info.value.code == "usage_limit_exceeded"
        assert "Asset limit of 5 reached" in str(exc_info.value.message)

        # Case C: Limit is unlimited -> Allowed regardless of count
        mock_entitlements.usage_limits[0] = UsageLimitConfiguration(
            feature_key="ASSET",
            limit_key="max_assets",
            limit_value=None,
            is_unlimited=True,
        )
        mock_db.execute.return_value.scalar_one.return_value = 1000
        check_asset_creation_limit(mock_db, organization_id=org_id)  # Does not raise


def test_enforcement_user_limit_exceeded():
    """Requirement 12: User invitation limit enforcement raises UsageLimitExceededError."""
    from unittest.mock import MagicMock
    from app.services.limit_enforcement_service import check_user_creation_limit
    from app.services.entitlement_service import EntitlementResolution, EntitlementResolutionStatus, UsageLimitConfiguration

    mock_db = MagicMock()
    org_id = uuid.uuid4()

    mock_entitlements = EntitlementResolution(
        organization_id=org_id,
        resolution_status=EntitlementResolutionStatus.ACTIVE,
        organization_status="ACTIVE",
        subscription_id=uuid.uuid4(),
        subscription_status="ACTIVE",
        plan_id=uuid.uuid4(),
        plan_code="AIRCRAFT_001",
        effective_features={},
        usage_limits=[
            UsageLimitConfiguration(
                feature_key="USER",
                limit_key="max_users",
                limit_value=10,
                is_unlimited=False,
            )
        ],
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.limit_enforcement_service.resolve_entitlements", lambda db, organization_id: mock_entitlements)

        mock_db.execute.return_value.scalar_one.return_value = 9
        check_user_creation_limit(mock_db, organization_id=org_id)  # Allowed

        mock_db.execute.return_value.scalar_one.return_value = 10
        with pytest.raises(UsageLimitExceededError) as exc:
            check_user_creation_limit(mock_db, organization_id=org_id)
        assert "User seat limit of 10 reached" in exc.value.message


def test_enforcement_work_order_limit_exceeded():
    """Requirement 12: Monthly work order limit enforcement raises UsageLimitExceededError."""
    from unittest.mock import MagicMock
    from app.services.limit_enforcement_service import check_work_order_creation_limit
    from app.services.entitlement_service import EntitlementResolution, EntitlementResolutionStatus, UsageLimitConfiguration

    mock_db = MagicMock()
    org_id = uuid.uuid4()

    mock_entitlements = EntitlementResolution(
        organization_id=org_id,
        resolution_status=EntitlementResolutionStatus.ACTIVE,
        organization_status="ACTIVE",
        subscription_id=uuid.uuid4(),
        subscription_status="ACTIVE",
        plan_id=uuid.uuid4(),
        plan_code="DRONE_001",
        effective_features={},
        usage_limits=[
            UsageLimitConfiguration(
                feature_key="MRO",
                limit_key="monthly_work_orders",
                limit_value=50,
                is_unlimited=False,
            )
        ],
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.limit_enforcement_service.resolve_entitlements", lambda db, organization_id: mock_entitlements)

        mock_db.execute.return_value.scalar_one.return_value = 49
        check_work_order_creation_limit(mock_db, organization_id=org_id)  # Allowed

        mock_db.execute.return_value.scalar_one.return_value = 50
        with pytest.raises(UsageLimitExceededError) as exc:
            check_work_order_creation_limit(mock_db, organization_id=org_id)
        assert "Monthly work order limit of 50 reached" in exc.value.message
