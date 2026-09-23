import uuid
import pytest
from app.core.errors import ConflictError, ForbiddenError
from app.core.permissions import Permission, Role, ROLE_PERMISSIONS, permissions_for_roles
from app.schemas.tenant import (
    TenantInvitationRequest,
    TenantProfileResponse,
    TenantUsageResponse,
    TenantUsageMetricItem,
)
from app.services.tenant_service import (
    SUPPORTED_TENANT_ROLES,
    ROLE_DESCRIPTIONS,
    list_tenant_roles,
)


def test_org_admin_has_tenant_permissions_and_no_platform_permissions():
    """Verify Tenant Admin (ORG_ADMIN) has org/user administration grants
    but strictly ZERO platform control plane permissions."""
    org_admin_perms = ROLE_PERMISSIONS[Role.ORG_ADMIN]
    
    # Must have tenant administration permissions
    assert Permission.ORG_MANAGE in org_admin_perms
    assert Permission.USER_MANAGE in org_admin_perms
    assert Permission.AUDIT_READ in org_admin_perms
    assert Permission.FACILITY_READ in org_admin_perms
    assert Permission.FACILITY_WRITE in org_admin_perms
    assert Permission.AIRCRAFT_READ in org_admin_perms
    assert Permission.DRONE_READ in org_admin_perms

    # Must NOT have platform permissions
    assert Permission.PLATFORM_MANAGE not in org_admin_perms
    assert Permission.PLATFORM_ENTITLEMENT_OVERRIDE not in org_admin_perms


def test_supported_tenant_roles_excludes_platform_staff_and_super_admin():
    """Verify the tenant administration layer never allows assigning or inviting
    platform roles (PLATFORM_ADMIN, PLATFORM_STAFF) or SUPER_ADMIN."""
    for role in SUPPORTED_TENANT_ROLES:
        assert role != Role.PLATFORM_ADMIN
        assert role != Role.PLATFORM_STAFF
        assert role != Role.SUPER_ADMIN
        assert role in ROLE_DESCRIPTIONS

    role_names = {r.value for r in SUPPORTED_TENANT_ROLES}
    assert "PLATFORM_ADMIN" not in role_names
    assert "PLATFORM_STAFF" not in role_names
    assert "SUPER_ADMIN" not in role_names
    assert "ORG_ADMIN" in role_names
    assert "CAMO_MANAGER" in role_names
    assert "VIEWER" in role_names


def test_list_tenant_roles_exposes_accurate_permission_catalog():
    """Verify list_tenant_roles accurately exposes permission strings for tenant roles."""
    roles = list_tenant_roles()
    assert len(roles) == len(SUPPORTED_TENANT_ROLES)
    
    org_admin_info = next(r for r in roles if r.role_name == Role.ORG_ADMIN.value)
    assert org_admin_info.is_system_role is True
    assert Permission.ORG_MANAGE.value in org_admin_info.permissions
    assert Permission.PLATFORM_MANAGE.value not in org_admin_info.permissions

    viewer_info = next(r for r in roles if r.role_name == Role.VIEWER.value)
    assert Permission.ORG_MANAGE.value not in viewer_info.permissions
    assert Permission.AIRCRAFT_READ.value in viewer_info.permissions


def test_tenant_usage_response_honestly_labels_unmetered_dimensions():
    """Verify unmetered dimensions are strictly marked tracked=False and NOT_TRACKED."""
    metrics = [
        TenantUsageMetricItem(
            key="user_seats",
            label="User Accounts",
            tracked=True,
            value=5,
            limit=25,
            unit="Seats",
            status="TRACKED",
        ),
        TenantUsageMetricItem(
            key="blob_storage",
            label="Storage",
            tracked=False,
            value=None,
            limit=None,
            unit="GB",
            status="NOT_TRACKED",
        ),
        TenantUsageMetricItem(
            key="api_bandwidth",
            label="API Traffic",
            tracked=False,
            value=None,
            limit=None,
            unit="Req/mo",
            status="NOT_TRACKED",
        ),
    ]
    resp = TenantUsageResponse(organization_id=uuid.uuid4(), metrics=metrics)
    assert resp.metrics[0].tracked is True
    assert resp.metrics[0].value == 5
    assert resp.metrics[1].tracked is False
    assert resp.metrics[1].value is None
    assert resp.metrics[1].status == "NOT_TRACKED"
    assert resp.metrics[2].tracked is False
    assert resp.metrics[2].status == "NOT_TRACKED"
