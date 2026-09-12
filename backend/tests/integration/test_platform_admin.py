"""Tests for platform-level administration: RBAC (customer users must get
403, never merely a hidden frontend route), organization lifecycle
(create/activate/suspend), suspended-org login refusal, and that
PLATFORM_ADMIN never implicitly gains customer operational permissions.
"""
import uuid

import pytest

from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.permissions import Permission, Role, permissions_for_roles
from app.models.organization import Organization, OrganizationStatus
from app.models.user import User, UserRole
from app.schemas.auth import CurrentUser
from app.services import auth_service, platform_service
from app.services.ai.tools import execute_tool


def _platform_admin_user(org_id: uuid.UUID) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        organization_id=org_id,
        email="platform-admin@kotas-aerospace.com",
        full_name="Platform Admin",
        roles=[Role.PLATFORM_ADMIN.value],
    )


def test_platform_admin_role_grants_only_platform_manage():
    granted = permissions_for_roles([Role.PLATFORM_ADMIN.value])
    assert granted == {Permission.PLATFORM_MANAGE.value}


def test_org_admin_role_does_not_grant_platform_manage():
    granted = permissions_for_roles([Role.ORG_ADMIN.value])
    assert Permission.PLATFORM_MANAGE.value not in granted


def test_customer_org_admin_cannot_call_platform_service_permission(db_session):
    from app.core.deps import require_permission

    org_id = uuid.uuid4()
    customer_admin = CurrentUser(
        id=uuid.uuid4(),
        organization_id=org_id,
        email="admin@customer.com",
        full_name="Customer Admin",
        roles=[Role.ORG_ADMIN.value],
    )
    checker = require_permission(Permission.PLATFORM_MANAGE)
    with pytest.raises(ForbiddenError):
        checker(current_user=customer_admin)


def test_platform_admin_can_create_activate_suspend_organization(db_session):
    admin = _platform_admin_user(uuid.uuid4())

    org = platform_service.create_organization(
        db_session, actor_user_id=admin.id, name="Test Customer MRO"
    )
    assert org.status == OrganizationStatus.ACTIVE

    suspended = platform_service.set_organization_status(
        db_session,
        actor_user_id=admin.id,
        organization_id=org.id,
        status=OrganizationStatus.SUSPENDED,
    )
    assert suspended.status == OrganizationStatus.SUSPENDED

    reactivated = platform_service.set_organization_status(
        db_session, actor_user_id=admin.id, organization_id=org.id, status=OrganizationStatus.ACTIVE
    )
    assert reactivated.status == OrganizationStatus.ACTIVE


def test_platform_admin_can_create_org_admin_for_new_tenant(db_session):
    admin = _platform_admin_user(uuid.uuid4())
    org = platform_service.create_organization(
        db_session, actor_user_id=admin.id, name="Onboarding Test MRO"
    )

    user = platform_service.create_organization_admin(
        db_session,
        actor_user_id=admin.id,
        organization_id=org.id,
        email="new-admin@onboarding-test.com",
        full_name="New Admin",
        password="supersecret123",
    )
    assert user.organization_id == org.id
    roles = db_session.query(UserRole).filter(UserRole.user_id == user.id).all()
    assert [r.role_name for r in roles] == [Role.ORG_ADMIN.value]


def test_suspended_organization_login_is_refused(db_session):
    org = Organization(name="Suspended Co", status=OrganizationStatus.SUSPENDED)
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email="user@suspended-co.com",
        hashed_password=auth_service.hash_password("supersecret123"),
        full_name="Suspended User",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    with pytest.raises(UnauthorizedError):
        auth_service.authenticate(db_session, "user@suspended-co.com", "supersecret123")


def test_list_organizations_reports_real_counts_not_fabricated(db_session):
    admin = _platform_admin_user(uuid.uuid4())
    org = platform_service.create_organization(
        db_session, actor_user_id=admin.id, name="Counted MRO"
    )

    rows = platform_service.list_organizations(db_session)
    row = next(r for r in rows if r["organization"].id == org.id)
    assert row["user_count"] == 0
    assert row["aircraft_count"] == 0

    platform_service.create_organization_admin(
        db_session,
        actor_user_id=admin.id,
        organization_id=org.id,
        email="admin@counted-mro.com",
        full_name="Admin",
        password="supersecret123",
    )
    rows = platform_service.list_organizations(db_session)
    row = next(r for r in rows if r["organization"].id == org.id)
    assert row["user_count"] == 1


def test_platform_admin_has_no_implicit_aircraft_access_via_tools(db_session):
    org_id = uuid.uuid4()
    admin = _platform_admin_user(org_id)
    with pytest.raises(ForbiddenError):
        execute_tool(db_session, admin, "list_aircraft", {})
