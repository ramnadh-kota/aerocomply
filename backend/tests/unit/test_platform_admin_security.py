import uuid
from datetime import datetime, UTC
import pytest

from app.core.permissions import Permission, Role, permissions_for_roles
from app.schemas.platform import (
    PlatformOrganizationResponse,
    PlatformUserResponse,
    PlatformDashboardStatsResponse,
    PlanDistributionItem,
    AuditEventResponse,
)


def test_platform_roles_and_tenant_role_separation():
    """Verify strictly that platform administration permissions are only granted to
    PLATFORM_ADMIN and PLATFORM_STAFF, and NEVER to any customer tenant role."""
    admin_perms = permissions_for_roles([Role.PLATFORM_ADMIN.value])
    assert Permission.PLATFORM_MANAGE.value in admin_perms
    assert Permission.PLATFORM_ENTITLEMENT_OVERRIDE.value in admin_perms

    staff_perms = permissions_for_roles([Role.PLATFORM_STAFF.value])
    assert Permission.PLATFORM_MANAGE.value in staff_perms
    # Platform staff must not hold expansive entitlement override authority
    assert Permission.PLATFORM_ENTITLEMENT_OVERRIDE.value not in staff_perms

    tenant_roles = [
        Role.ORG_ADMIN,
        Role.COMPLIANCE_MANAGER,
        Role.CAMO_MANAGER,
        Role.QUALITY_MANAGER,
        Role.MAINTENANCE_ENGINEER,
        Role.VIEWER,
    ]
    for r in tenant_roles:
        perms = permissions_for_roles([r.value])
        assert Permission.PLATFORM_MANAGE.value not in perms, f"Role {r} leaked PLATFORM_MANAGE"
        assert (
            Permission.PLATFORM_ENTITLEMENT_OVERRIDE.value not in perms
        ), f"Role {r} leaked PLATFORM_ENTITLEMENT_OVERRIDE"


def test_platform_organization_schema_includes_drones():
    """Verify PlatformOrganizationResponse includes user_count, aircraft_count, and drone_count."""
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    resp = PlatformOrganizationResponse(
        id=org_id,
        name="Drone Operations Corp",
        status="ACTIVE",
        industry="DRONE_UAV",
        created_at=now,
        user_count=8,
        aircraft_count=0,
        drone_count=12,
    )
    assert resp.id == org_id
    assert resp.name == "Drone Operations Corp"
    assert resp.industry == "DRONE_UAV"
    assert resp.user_count == 8
    assert resp.aircraft_count == 0
    assert resp.drone_count == 12


def test_platform_user_response_schema():
    """Verify PlatformUserResponse correctly structures tenant user inspection."""
    uid = uuid.uuid4()
    org_id = uuid.uuid4()
    now = datetime.now(UTC)
    resp = PlatformUserResponse(
        id=uid,
        organization_id=org_id,
        organization_name="Horizon Drone Services",
        email="operator@horizon.com",
        full_name="Alex Rivera",
        is_active=True,
        roles=["ORG_ADMIN", "CHIEF_PILOT"],
        created_at=now,
    )
    assert resp.id == uid
    assert resp.organization_name == "Horizon Drone Services"
    assert "ORG_ADMIN" in resp.roles
    assert resp.is_active is True


def test_platform_dashboard_stats_schema():
    """Verify PlatformDashboardStatsResponse aggregates KPIs cleanly."""
    stats = PlatformDashboardStatsResponse(
        total_organizations=5,
        active_organizations=4,
        suspended_organizations=1,
        pending_provisioning=0,
        active_subscriptions=4,
        trial_subscriptions=1,
        total_users=35,
        total_aircraft=12,
        total_drones=18,
        organizations_by_plan=[
            PlanDistributionItem(plan_code="enterprise", plan_name="Enterprise Control", count=1),
            PlanDistributionItem(plan_code="professional", plan_name="Professional Ops", count=3),
        ],
        recent_activity=[],
    )
    assert stats.total_organizations == 5
    assert stats.active_organizations == 4
    assert stats.total_drones == 18
    assert len(stats.organizations_by_plan) == 2
    assert stats.organizations_by_plan[0].plan_code == "enterprise"
