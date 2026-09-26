"""Integration tests for Plan Usage Limits:
Persistence, Bulk API, Inheritance, Tenant Overrides, Audit, and Enforcement.

Covers all 12 core requirements:
1. Create Plan with limits.
2. Update Plan limits.
3. Remove a plan limit.
4. Unlimited limit.
5. Duplicate limit key rejected/prevented.
6. Tenant inherits plan limit.
7. Feature entitlement remains separate from usage limit.
8. Tenant override behavior remains intact.
9. Platform Admin can modify plan limits.
10. ORG_ADMIN cannot modify global plan limits.
11. Audit event generated.
12. Usage enforcement respects effective limit.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.errors import ConflictError, UsageLimitExceededError
from app.models.asset import Asset, AssetType
from app.models.audit_event import AuditEvent
from app.models.organization import Organization, OrganizationStatus
from app.models.plan import Plan, PlanFeature, PlanLimit
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.models.user import User, UserRole
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.asset import AssetCreateRequest
from app.schemas.tenant import TenantInvitationRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, asset_service, plan_service, tenant_service, work_order_service
from app.services.entitlement_service import resolve_entitlements
from app.services.limit_enforcement_service import (
    check_asset_creation_limit,
    check_user_creation_limit,
    check_work_order_creation_limit,
)


def _setup_platform_admin(db_session):
    org = Organization(name="Kota Platform Admin Org", status=OrganizationStatus.ACTIVE)
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"admin_{uuid.uuid4().hex[:6]}@aerocomply.com",
        full_name="Platform Administrator",
        hashed_password="hashed_pass_placeholder",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()
    return org, user


def _setup_tenant_and_subscription(db_session, plan):
    org = Organization(name=f"Customer Tenant {uuid.uuid4().hex[:6]}", status=OrganizationStatus.ACTIVE)
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"tenant_admin_{uuid.uuid4().hex[:6]}@customer.com",
        full_name="Tenant Admin",
        hashed_password="hashed_pass_placeholder",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    db_session.add(UserRole(user_id=user.id, role_name="ORG_ADMIN", organization_id=org.id))

    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC),
    )
    db_session.add(sub)
    db_session.commit()
    return org, user, sub


# 1. Create Plan with limits & 4. Unlimited limit
def test_create_plan_and_bulk_set_limits(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="Drone Commercial Pro",
        code=f"DRONE_PRO_{uuid.uuid4().hex[:6]}",
        asset_scope="DRONE",
    )

    limits_payload = [
        {"limit_key": "max_assets", "limit_value": 100, "is_unlimited": False},
        {"limit_key": "max_users", "limit_value": 25, "is_unlimited": False},
        {"limit_key": "storage_gb", "limit_value": None, "is_unlimited": True},
    ]

    saved_limits = plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=limits_payload,
    )

    assert len(saved_limits) == 3
    limits_map = {l.limit_key: l for l in saved_limits}
    assert limits_map["max_assets"].limit_value == 100
    assert limits_map["max_assets"].is_unlimited is False
    assert limits_map["max_users"].limit_value == 25
    assert limits_map["storage_gb"].is_unlimited is True
    assert limits_map["storage_gb"].limit_value is None


# 2. Update Plan limits & 11. Audit events generated
def test_update_plan_limits_and_audit(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="Aircraft Enterprise",
        code=f"AIR_ENT_{uuid.uuid4().hex[:6]}",
        asset_scope="AIRCRAFT",
    )

    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[
            {"limit_key": "max_assets", "limit_value": 50, "is_unlimited": False},
        ],
    )

    # Update limit to 75
    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[
            {"limit_key": "max_assets", "limit_value": 75, "is_unlimited": False},
        ],
    )

    limits = plan_service.list_plan_limits(db_session, plan_id=plan.id)
    assert len(limits) == 1
    assert limits[0].limit_value == 75

    # Verify audit trail
    events = list(
        db_session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == "PlanLimit",
                AuditEvent.action == "platform.plan_limit.updated",
            )
        )
        .scalars()
        .all()
    )
    assert len(events) >= 1
    event = events[-1]
    assert event.event_metadata["previous_value"] == 50
    assert event.event_metadata["new_value"] == 75
    assert event.event_metadata["limit_key"] == "max_assets"


# 3. Remove a plan limit
def test_remove_plan_limit_on_exclusion(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="Helicopter Plan",
        code=f"HELI_{uuid.uuid4().hex[:6]}",
        asset_scope="HELICOPTER",
    )

    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[
            {"limit_key": "max_assets", "limit_value": 30, "is_unlimited": False},
            {"limit_key": "monthly_work_orders", "limit_value": 600, "is_unlimited": False},
        ],
    )
    assert len(plan_service.list_plan_limits(db_session, plan_id=plan.id)) == 2

    # Now exclude monthly_work_orders
    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[
            {"limit_key": "max_assets", "limit_value": 30, "is_unlimited": False},
        ],
    )

    remaining = plan_service.list_plan_limits(db_session, plan_id=plan.id)
    assert len(remaining) == 1
    assert remaining[0].limit_key == "max_assets"


# 5. Duplicate limit key rejected
def test_duplicate_limit_key_rejected(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="eVTOL Plan",
        code=f"EVTOL_{uuid.uuid4().hex[:6]}",
        asset_scope="EVTOL",
    )

    duplicate_payload = [
        {"limit_key": "max_assets", "limit_value": 75, "is_unlimited": False},
        {"limit_key": "max_assets", "limit_value": 100, "is_unlimited": False},
    ]

    with pytest.raises(ConflictError) as exc_info:
        plan_service.bulk_set_plan_limits(
            db_session,
            actor_user_id=admin_user.id,
            actor_organization_id=admin_org.id,
            plan_id=plan.id,
            limits=duplicate_payload,
        )
    assert "Duplicate limit key" in str(exc_info.value)


# 6. Tenant inherits plan limit & 7. Feature entitlement remains separate from usage limit
def test_tenant_inherits_plan_limit_and_separate_from_features(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="Kota Drone Tier 1",
        code=f"DRONE_T1_{uuid.uuid4().hex[:6]}",
        asset_scope="DRONE",
    )

    # Feature: drone_fleet_management = True
    plan_service.create_plan_feature(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        feature_key="drone_fleet_management",
        enabled=True,
    )

    # Limit: max_assets = 100
    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[{"limit_key": "max_assets", "limit_value": 100, "is_unlimited": False}],
    )

    # Tenant subscribes to plan
    cust_org, cust_admin, _ = _setup_tenant_and_subscription(db_session, plan)

    resolution = resolve_entitlements(db_session, organization_id=cust_org.id)

    # Verify Feature Entitlement
    assert resolution.effective_features.get("drone_fleet_management") is True

    # Verify Inherited Usage Limit
    limit_conf = next((l for l in resolution.usage_limits if l.limit_key == "max_assets"), None)
    assert limit_conf is not None
    assert limit_conf.limit_value == 100
    assert limit_conf.is_unlimited is False


# 8. Tenant override behavior remains intact
def test_tenant_override_takes_precedence_over_plan_baseline(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="Kota Drone Baseline",
        code=f"DRONE_BASE_{uuid.uuid4().hex[:6]}",
        asset_scope="DRONE",
    )

    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[{"limit_key": "max_assets", "limit_value": 100, "is_unlimited": False}],
    )

    cust_org, _, _ = _setup_tenant_and_subscription(db_session, plan)

    # Baseline check: 100
    res1 = resolve_entitlements(db_session, organization_id=cust_org.id)
    assert next(l for l in res1.usage_limits if l.limit_key == "max_assets").limit_value == 100

    # Apply TenantUsageLimit override: 150
    tenant_override = TenantUsageLimit(
        organization_id=cust_org.id,
        feature_key="fleet",
        limit_key="max_assets",
        limit_value=150,
        is_unlimited=False,
    )
    db_session.add(tenant_override)
    db_session.commit()

    # Override check: 150 wins over plan's 100
    res2 = resolve_entitlements(db_session, organization_id=cust_org.id)
    override_limit = next(l for l in res2.usage_limits if l.limit_key == "max_assets")
    assert override_limit.limit_value == 150

    # If the plan baseline changes to 120, the tenant override still wins (150)
    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[{"limit_key": "max_assets", "limit_value": 120, "is_unlimited": False}],
    )
    res3 = resolve_entitlements(db_session, organization_id=cust_org.id)
    assert next(l for l in res3.usage_limits if l.limit_key == "max_assets").limit_value == 150


# 9. Platform Admin can modify plan limits & 10. ORG_ADMIN cannot modify via API
def test_platform_admin_vs_org_admin_authorization(client, db_session):
    from tests.integration.conftest import make_platform_admin_headers

    admin_headers = make_platform_admin_headers(client, db_session)

    # 1. Platform Admin creates plan
    plan_resp = client.post(
        "/api/v1/platform/plans",
        headers=admin_headers,
        json={"name": "API Governance Plan", "code": f"GOV_{uuid.uuid4().hex[:6]}"},
    )
    assert plan_resp.status_code == 201
    plan_id = plan_resp.json()["id"]

    # 2. Platform Admin sets limits -> 200 OK
    put_resp = client.put(
        f"/api/v1/platform/plans/{plan_id}/limits",
        headers=admin_headers,
        json={
            "limits": [
                {"limit_key": "max_assets", "limit_value": 200, "is_unlimited": False},
                {"limit_key": "storage_gb", "is_unlimited": True},
            ]
        },
    )
    assert put_resp.status_code == 200
    assert len(put_resp.json()) == 2

    # 3. Create non-platform org admin
    customer_org = Organization(name="Customer Corp", status=OrganizationStatus.ACTIVE)
    db_session.add(customer_org)
    db_session.flush()

    customer_user = User(
        organization_id=customer_org.id,
        email=f"customer_admin_{uuid.uuid4().hex[:6]}@corp.com",
        full_name="Customer Org Admin",
        hashed_password="hashed_pass_placeholder",
        is_active=True,
    )
    db_session.add(customer_user)
    db_session.flush()
    db_session.add(UserRole(user_id=customer_user.id, role_name="ORG_ADMIN", organization_id=customer_org.id))
    db_session.commit()

    from app.core.security import create_access_token
    token = create_access_token(
        user_id=customer_user.id,
        organization_id=customer_org.id,
        roles=["ORG_ADMIN"],
        email=customer_user.email,
        full_name=customer_user.full_name,
        email_verified=True,
    )
    customer_headers = {"Authorization": f"Bearer {token}"}

    # 4. ORG_ADMIN attempts to modify plan limits -> 403 Forbidden
    cust_put_resp = client.put(
        f"/api/v1/platform/plans/{plan_id}/limits",
        headers=customer_headers,
        json={"limits": [{"limit_key": "max_assets", "limit_value": 9999, "is_unlimited": False}]},
    )
    assert cust_put_resp.status_code == 403


# 12. Usage enforcement respects effective limit
def test_usage_enforcement_blocks_asset_creation_when_limit_reached(db_session):
    admin_org, admin_user = _setup_platform_admin(db_session)
    plan = plan_service.create_plan(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        name="Restricted Plan",
        code=f"RESTRICT_{uuid.uuid4().hex[:6]}",
        asset_scope="DRONE",
    )

    # Set plan limit: max_assets = 1
    plan_service.bulk_set_plan_limits(
        db_session,
        actor_user_id=admin_user.id,
        actor_organization_id=admin_org.id,
        plan_id=plan.id,
        limits=[{"limit_key": "max_assets", "limit_value": 1, "is_unlimited": False}],
    )

    cust_org, cust_admin, _ = _setup_tenant_and_subscription(db_session, plan)

    # First asset: succeeds (count becomes 1)
    asset1 = asset_service.create_asset(
        db_session,
        organization_id=cust_org.id,
        actor_user_id=cust_admin.id,
        payload=AssetCreateRequest(
            asset_type="DRONE",
            registration="DRN-001",
            manufacturer="DJI",
            model="M300",
        ),
    )
    assert asset1.id is not None
    db_session.commit()

    # Second asset: exceeds limit -> raises UsageLimitExceededError
    with pytest.raises(UsageLimitExceededError) as exc_info:
        asset_service.create_asset(
            db_session,
            organization_id=cust_org.id,
            actor_user_id=cust_admin.id,
            payload=AssetCreateRequest(
                asset_type="DRONE",
                registration="DRN-002",
                manufacturer="DJI",
                model="M300",
            ),
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "usage_limit_exceeded"
    assert "Asset limit of 1 reached" in exc_info.value.message
