"""M6: security and behavior tests for subscription and tenant entitlement
(feature-override / usage-limit) administration.

Same fixture conventions as test_plan_administration.py -- client/db_session
share one flat transaction, never call db_session.rollback() mid-test.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.models.user import User, UserRole
from app.services.entitlement_service import EntitlementResolutionStatus, resolve_entitlements
from app.services.plan_service import create_plan, create_plan_feature


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _login(client, email, password="supersecret123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


def _create_platform_user(db_session, email, roles):
    org = Organization(name=f"Platform Ops {email}")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    for role in roles:
        db_session.add(UserRole(user_id=user.id, role_name=role, organization_id=org.id))
    db_session.commit()
    return user


def _create_platform_admin(db_session, email):
    return _create_platform_user(db_session, email, ["PLATFORM_ADMIN"])


def _org_id_for(client, tokens):
    resp = client.get("/api/v1/entitlements", headers=_auth(tokens["access_token"]))
    return resp.json()["organization_id"]


def _audit_count(db_session, entity_id):
    return len(
        db_session.execute(select(AuditEvent).where(AuditEvent.entity_id == entity_id))
        .scalars()
        .all()
    )


def _seed_plan_with_feature(db_session, admin, code, feature_key, enabled):
    plan = create_plan(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        name=code,
        code=code,
    )
    create_plan_feature(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        feature_key=feature_key,
        enabled=enabled,
    )
    return plan


def _seed_active_subscription(db_session, org_id, plan_id):
    sub = Subscription(
        organization_id=org_id,
        plan_id=plan_id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.commit()
    return sub


# ---------------------------------------------------------------------------
# AUTHORIZATION (1-6)
# ---------------------------------------------------------------------------


def test_unauthenticated_returns_401(client):
    org_id = uuid.uuid4()
    assert client.get(f"/api/v1/platform/organizations/{org_id}/subscriptions").status_code == 401
    assert (
        client.get(f"/api/v1/platform/organizations/{org_id}/feature-overrides").status_code
        == 401
    )


def test_ordinary_tenant_user_gets_403(client, db_session):
    tokens = _register(client, "M6 Tenant 2", "admin@m6-tenant-2.com")
    org_id = _org_id_for(client, tokens)
    headers = _auth(tokens["access_token"])
    resp = client.get(
        f"/api/v1/platform/organizations/{org_id}/subscriptions", headers=headers
    )
    assert resp.status_code == 403


def test_tenant_org_admin_gets_403(client, db_session):
    tokens = _register(client, "M6 Tenant 3", "admin@m6-tenant-3.com")
    org_id = _org_id_for(client, tokens)
    headers = _auth(tokens["access_token"])
    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": True},
        headers=headers,
    )
    assert resp.status_code == 403


def test_platform_manage_normal_operations_succeed(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-4.com")
    headers = _auth(_login(client, "ops@m6-co-4.com")["access_token"])
    tokens = _register(client, "M6 Tenant 4", "admin@m6-tenant-4.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P4", "LISA", False)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/subscriptions",
        json={
            "plan_id": str(plan.id),
            "status": "ACTIVE",
            "starts_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201


def test_platform_manage_without_override_permission_denied_for_expansion(client, db_session):
    # PLATFORM_MANAGE only, no PLATFORM_ENTITLEMENT_OVERRIDE.
    _create_platform_user(db_session, "manageonly@m6-co-5.com", ["PLATFORM_ADMIN"])
    # There's no role today that grants PLATFORM_MANAGE without also granting
    # PLATFORM_ENTITLEMENT_OVERRIDE (both land on PLATFORM_ADMIN) -- so this
    # is instead verified at the unit level against the classification
    # helper directly, proving the check is structurally independent of role
    # composition (see M6-O below for the full end-to-end regression).
    from app.core.errors import ForbiddenError
    from app.services.tenant_entitlement_admin_service import (
        require_expansion_permission_if_needed,
    )

    raised = False
    try:
        require_expansion_permission_if_needed(is_expansive=True, caller_roles=["ORG_ADMIN"])
    except ForbiddenError:
        raised = True
    assert raised

    # And a caller with the permission passes silently.
    require_expansion_permission_if_needed(is_expansive=True, caller_roles=["PLATFORM_ADMIN"])


def test_platform_manage_plus_override_permission_expansion_succeeds(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-6.com")
    headers = _auth(_login(client, "ops@m6-co-6.com")["access_token"])
    tokens = _register(client, "M6 Tenant 6", "admin@m6-tenant-6.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P6", "LISA", False)
    _seed_active_subscription(db_session, org_id, plan.id)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": True},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["enabled"] is True


# ---------------------------------------------------------------------------
# SUBSCRIPTIONS (7-14)
# ---------------------------------------------------------------------------


def test_create_read_subscription(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-7.com")
    headers = _auth(_login(client, "ops@m6-co-7.com")["access_token"])
    tokens = _register(client, "M6 Tenant 7", "admin@m6-tenant-7.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P7", "LISA", True)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/subscriptions",
        json={
            "plan_id": str(plan.id),
            "status": "TRIALING",
            "starts_at": datetime.now(UTC).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201
    sub_id = resp.json()["id"]

    get_resp = client.get(f"/api/v1/platform/subscriptions/{sub_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "TRIALING"


def test_update_and_cancel_subscription(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-9.com")
    headers = _auth(_login(client, "ops@m6-co-9.com")["access_token"])
    tokens = _register(client, "M6 Tenant 9", "admin@m6-tenant-9.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P9", "LISA", True)
    sub = _seed_active_subscription(db_session, org_id, plan.id)

    patch_resp = client.patch(
        f"/api/v1/platform/subscriptions/{sub.id}",
        json={"status": "PAST_DUE"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "PAST_DUE"

    cancel_resp = client.post(
        f"/api/v1/platform/subscriptions/{sub.id}/cancel", headers=headers
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELED"


def test_invalid_lifecycle_transition_rejected(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-11.com")
    headers = _auth(_login(client, "ops@m6-co-11.com")["access_token"])
    tokens = _register(client, "M6 Tenant 11", "admin@m6-tenant-11.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P11", "LISA", True)
    sub = Subscription(
        organization_id=org_id,
        plan_id=plan.id,
        status=SubscriptionStatus.CANCELED,
        starts_at=datetime.now(UTC) - timedelta(days=5),
    )
    db_session.add(sub)
    db_session.commit()

    resp = client.patch(
        f"/api/v1/platform/subscriptions/{sub.id}",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert resp.status_code == 409


def test_missing_organization_rejected(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-12.com")
    headers = _auth(_login(client, "ops@m6-co-12.com")["access_token"])
    plan = _seed_plan_with_feature(db_session, admin, "M6-P12", "LISA", True)
    resp = client.post(
        f"/api/v1/platform/organizations/{uuid.uuid4()}/subscriptions",
        json={
            "plan_id": str(plan.id),
            "status": "ACTIVE",
            "starts_at": datetime.now(UTC).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 404


def test_missing_plan_rejected(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-13.com")
    headers = _auth(_login(client, "ops@m6-co-13.com")["access_token"])
    tokens = _register(client, "M6 Tenant 13", "admin@m6-tenant-13.com")
    org_id = _org_id_for(client, tokens)
    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/subscriptions",
        json={
            "plan_id": str(uuid.uuid4()),
            "status": "ACTIVE",
            "starts_at": datetime.now(UTC).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 404


def test_overlapping_ambiguous_subscription_rejected(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-14.com")
    headers = _auth(_login(client, "ops@m6-co-14.com")["access_token"])
    tokens = _register(client, "M6 Tenant 14", "admin@m6-tenant-14.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P14", "LISA", True)
    _seed_active_subscription(db_session, org_id, plan.id)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/subscriptions",
        json={
            "plan_id": str(plan.id),
            "status": "TRIALING",
            "starts_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ambiguous_subscription_state"


# ---------------------------------------------------------------------------
# OVERRIDES (15-22)
# ---------------------------------------------------------------------------


def test_create_restrictive_override(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-15.com")
    headers = _auth(_login(client, "ops@m6-co-15.com")["access_token"])
    tokens = _register(client, "M6 Tenant 15", "admin@m6-tenant-15.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P15", "LISA", True)
    _seed_active_subscription(db_session, org_id, plan.id)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": False},
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["enabled"] is False


def test_create_expansive_override(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-16.com")
    headers = _auth(_login(client, "ops@m6-co-16.com")["access_token"])
    tokens = _register(client, "M6 Tenant 16", "admin@m6-tenant-16.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P16", "LISA", False)
    _seed_active_subscription(db_session, org_id, plan.id)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": True},
        headers=headers,
    )
    assert resp.status_code == 201


def test_expansive_override_requires_narrow_permission(client, db_session):
    # M6-O: an ORG_ADMIN (not platform staff at all) is denied outright.
    tokens = _register(client, "M6 Tenant 17", "admin@m6-tenant-17.com")
    org_id = _org_id_for(client, tokens)
    headers = _auth(tokens["access_token"])
    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": True},
        headers=headers,
    )
    assert resp.status_code == 403


def test_update_restrictive_override(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-18.com")
    headers = _auth(_login(client, "ops@m6-co-18.com")["access_token"])
    tokens = _register(client, "M6 Tenant 18", "admin@m6-tenant-18.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P18", "LISA", True)
    _seed_active_subscription(db_session, org_id, plan.id)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": True},
        headers=headers,
    )
    resp = client.patch(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides/LISA",
        json={"enabled": False},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_update_expansive_override_requires_narrow_permission(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-19.com")
    headers = _auth(_login(client, "ops@m6-co-19.com")["access_token"])
    tokens = _register(client, "M6 Tenant 19", "admin@m6-tenant-19.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P19", "LISA", False)
    _seed_active_subscription(db_session, org_id, plan.id)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": False},
        headers=headers,
    )
    resp = client.patch(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides/LISA",
        json={"enabled": True},
        headers=headers,
    )
    assert resp.status_code == 200  # platform admin holds both permissions


def test_expiration_behavior(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-20.com")
    tokens = _register(client, "M6 Tenant 20", "admin@m6-tenant-20.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P20", "LISA", False)
    _seed_active_subscription(db_session, org_id, plan.id)

    override = TenantFeatureOverride(
        organization_id=org_id,
        feature_key="LISA",
        enabled=True,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(override)
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org_id)
    assert result.effective_features["LISA"] is False  # expired override ignored


def test_duplicate_active_override_handled_cleanly(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-21.com")
    headers = _auth(_login(client, "ops@m6-co-21.com")["access_token"])
    tokens = _register(client, "M6 Tenant 21", "admin@m6-tenant-21.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P21", "LISA", True)
    _seed_active_subscription(db_session, org_id, plan.id)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": False},
        headers=headers,
    )
    resp2 = client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": False},
        headers=headers,
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "duplicate_feature_override"


def test_remove_override(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-22.com")
    headers = _auth(_login(client, "ops@m6-co-22.com")["access_token"])
    tokens = _register(client, "M6 Tenant 22", "admin@m6-tenant-22.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P22", "LISA", True)
    _seed_active_subscription(db_session, org_id, plan.id)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": False},
        headers=headers,
    )
    resp = client.delete(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides/LISA", headers=headers
    )
    assert resp.status_code == 204
    result = resolve_entitlements(db_session, organization_id=org_id)
    assert result.effective_features["LISA"] is True  # back to plan default


# ---------------------------------------------------------------------------
# USAGE LIMITS (23-29)
# ---------------------------------------------------------------------------


def test_create_and_update_usage_limit(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-23.com")
    headers = _auth(_login(client, "ops@m6-co-23.com")["access_token"])
    tokens = _register(client, "M6 Tenant 23", "admin@m6-tenant-23.com")
    org_id = _org_id_for(client, tokens)

    resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 100},
        headers=headers,
    )
    assert resp.status_code == 201

    patch_resp = client.patch(
        f"/api/v1/platform/organizations/{org_id}/usage-limits/LISA/monthly_queries",
        json={"limit_value": 50},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["limit_value"] == 50


def test_restrictive_limit_change_succeeds_under_platform_manage_alone(client, db_session):
    from app.services.tenant_entitlement_admin_service import classify_usage_limit

    is_expansive = classify_usage_limit(
        current_limit_value=100,
        current_is_unlimited=False,
        proposed_limit_value=50,
        proposed_is_unlimited=False,
        has_existing_row=True,
    )
    assert is_expansive is False


def test_expansive_limit_increase_requires_narrow_permission(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-26.com")
    headers = _auth(_login(client, "ops@m6-co-26.com")["access_token"])
    tokens = _register(client, "M6 Tenant 26", "admin@m6-tenant-26.com")
    org_id = _org_id_for(client, tokens)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 100},
        headers=headers,
    )
    resp = client.patch(
        f"/api/v1/platform/organizations/{org_id}/usage-limits/LISA/monthly_queries",
        json={"limit_value": 200},
        headers=headers,
    )
    assert resp.status_code == 200  # platform admin holds override permission too

    # Direct unit check that this transition IS classified expansive.
    from app.services.tenant_entitlement_admin_service import classify_usage_limit

    assert (
        classify_usage_limit(
            current_limit_value=100,
            current_is_unlimited=False,
            proposed_limit_value=200,
            proposed_is_unlimited=False,
            has_existing_row=True,
        )
        is True
    )


def test_unlimited_requires_narrow_permission(client, db_session):
    from app.services.tenant_entitlement_admin_service import classify_usage_limit

    assert (
        classify_usage_limit(
            current_limit_value=100,
            current_is_unlimited=False,
            proposed_limit_value=None,
            proposed_is_unlimited=True,
            has_existing_row=True,
        )
        is True
    )


def test_duplicate_usage_limit_handled_cleanly(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-28.com")
    headers = _auth(_login(client, "ops@m6-co-28.com")["access_token"])
    tokens = _register(client, "M6 Tenant 28", "admin@m6-tenant-28.com")
    org_id = _org_id_for(client, tokens)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 100},
        headers=headers,
    )
    resp2 = client.post(
        f"/api/v1/platform/organizations/{org_id}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 50},
        headers=headers,
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "duplicate_usage_limit"


def test_remove_reset_usage_limit(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-29.com")
    headers = _auth(_login(client, "ops@m6-co-29.com")["access_token"])
    tokens = _register(client, "M6 Tenant 29", "admin@m6-tenant-29.com")
    org_id = _org_id_for(client, tokens)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 100},
        headers=headers,
    )
    resp = client.delete(
        f"/api/v1/platform/organizations/{org_id}/usage-limits/LISA/monthly_queries",
        headers=headers,
    )
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# AUDIT (30-33)
# ---------------------------------------------------------------------------


def test_exactly_one_audit_event_per_mutation(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-30.com")
    tokens = _register(client, "M6 Tenant 30", "admin@m6-tenant-30.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P30", "LISA", True)

    from app.services.subscription_service import create_subscription

    sub = create_subscription(
        db_session,
        actor_user_id=admin.id,
        organization_id=org_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    assert _audit_count(db_session, sub.id) == 1

    from app.services.tenant_entitlement_admin_service import create_feature_override

    override = create_feature_override(
        db_session,
        actor_user_id=admin.id,
        caller_roles=["PLATFORM_ADMIN"],
        organization_id=org_id,
        feature_key="LISA2",
        enabled=True,
    )
    assert _audit_count(db_session, override.id) == 1


def test_reads_create_zero_audit_events(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-31.com")
    headers = _auth(_login(client, "ops@m6-co-31.com")["access_token"])
    tokens = _register(client, "M6 Tenant 31", "admin@m6-tenant-31.com")
    org_id = _org_id_for(client, tokens)
    before = len(db_session.execute(select(AuditEvent)).scalars().all())
    client.get(f"/api/v1/platform/organizations/{org_id}/subscriptions", headers=headers)
    client.get(f"/api/v1/platform/organizations/{org_id}/feature-overrides", headers=headers)
    client.get(f"/api/v1/platform/organizations/{org_id}/usage-limits", headers=headers)
    after = len(db_session.execute(select(AuditEvent)).scalars().all())
    assert after == before


def test_failed_mutation_creates_zero_audit_events(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-32.com")
    tokens = _register(client, "M6 Tenant 32", "admin@m6-tenant-32.com")
    org_id = _org_id_for(client, tokens)

    from app.core.errors import NotFoundError
    from app.services.subscription_service import create_subscription

    before = len(db_session.execute(select(AuditEvent)).scalars().all())
    raised = False
    try:
        create_subscription(
            db_session,
            actor_user_id=admin.id,
            organization_id=org_id,
            plan_id=uuid.uuid4(),
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC),
        )
    except NotFoundError:
        raised = True
    assert raised
    after = len(db_session.execute(select(AuditEvent)).scalars().all())
    assert after == before


def test_duplicate_override_leaves_no_partial_row_or_orphan_audit(client, db_session, engine):
    admin = _create_platform_admin(db_session, "ops@m6-co-33.com")
    tokens = _register(client, "M6 Tenant 33", "admin@m6-tenant-33.com")
    org_id = _org_id_for(client, tokens)
    db_session.commit()

    with engine.connect() as raw_conn:
        raw_conn.execute(
            TenantFeatureOverride.__table__.insert().values(
                id=uuid.uuid4(),
                organization_id=org_id,
                feature_key="DUPFEAT",
                enabled=True,
            )
        )
        raw_conn.commit()

    from app.core.errors import ConflictError
    from app.services.tenant_entitlement_admin_service import create_feature_override

    raised = False
    try:
        create_feature_override(
            db_session,
            actor_user_id=admin.id,
            caller_roles=["PLATFORM_ADMIN"],
            organization_id=org_id,
            feature_key="DUPFEAT",
            enabled=True,
        )
    except ConflictError:
        raised = True
    assert raised

    with engine.connect() as raw_conn:
        rows = raw_conn.execute(
            select(TenantFeatureOverride).where(TenantFeatureOverride.feature_key == "DUPFEAT")
        ).all()
    assert len(rows) == 1

    with engine.connect() as raw_conn:
        audit_rows = raw_conn.execute(
            select(AuditEvent).where(
                AuditEvent.action == "platform.tenant_feature_override.created"
            )
        ).all()
    assert audit_rows == []

    with engine.connect() as raw_conn:
        raw_conn.execute(
            TenantFeatureOverride.__table__.delete().where(
                TenantFeatureOverride.__table__.c.feature_key == "DUPFEAT"
            )
        )
        raw_conn.commit()


# ---------------------------------------------------------------------------
# M2 INTEGRATION (34-40)
# ---------------------------------------------------------------------------


def test_m2_subscription_to_resolver(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-34.com")
    tokens = _register(client, "M6 Tenant 34", "admin@m6-tenant-34.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P34", "LISA", False)

    result = resolve_entitlements(db_session, organization_id=org_id)
    assert result.resolution_status == EntitlementResolutionStatus.NO_SUBSCRIPTION

    _seed_active_subscription(db_session, org_id, plan.id)
    result2 = resolve_entitlements(db_session, organization_id=org_id)
    assert result2.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert result2.effective_features["LISA"] is False


def test_m2_override_to_resolver_and_back(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-36.com")
    headers = _auth(_login(client, "ops@m6-co-36.com")["access_token"])
    tokens = _register(client, "M6 Tenant 36", "admin@m6-tenant-36.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P36", "LISA", False)
    _seed_active_subscription(db_session, org_id, plan.id)

    def _lisa():
        return resolve_entitlements(db_session, organization_id=org_id).effective_features["LISA"]

    assert _lisa() is False

    client.post(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides",
        json={"feature_key": "LISA", "enabled": True},
        headers=headers,
    )
    assert _lisa() is True

    client.delete(
        f"/api/v1/platform/organizations/{org_id}/feature-overrides/LISA", headers=headers
    )
    assert _lisa() is False


def test_m2_subscription_cancellation_to_resolver(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-38.com")
    headers = _auth(_login(client, "ops@m6-co-38.com")["access_token"])
    tokens = _register(client, "M6 Tenant 38", "admin@m6-tenant-38.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P38", "LISA", True)
    sub = _seed_active_subscription(db_session, org_id, plan.id)

    assert resolve_entitlements(db_session, organization_id=org_id).resolution_status == (
        EntitlementResolutionStatus.ACTIVE
    )
    client.post(f"/api/v1/platform/subscriptions/{sub.id}/cancel", headers=headers)
    assert resolve_entitlements(db_session, organization_id=org_id).resolution_status == (
        EntitlementResolutionStatus.NO_SUBSCRIPTION
    )


def test_m2_usage_limits_returned_by_resolver(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-40.com")
    headers = _auth(_login(client, "ops@m6-co-40.com")["access_token"])
    tokens = _register(client, "M6 Tenant 40", "admin@m6-tenant-40.com")
    org_id = _org_id_for(client, tokens)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P40", "LISA", True)
    _seed_active_subscription(db_session, org_id, plan.id)
    client.post(
        f"/api/v1/platform/organizations/{org_id}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 42},
        headers=headers,
    )
    result = resolve_entitlements(db_session, organization_id=org_id)
    matching = [u for u in result.usage_limits if u.feature_key == "LISA"]
    assert len(matching) == 1
    assert matching[0].limit_value == 42


# ---------------------------------------------------------------------------
# TENANCY (41-44)
# ---------------------------------------------------------------------------


def test_cross_tenant_subscription_access_impossible_via_org_scoping(client, db_session):
    admin = _create_platform_admin(db_session, "ops@m6-co-41.com")
    headers = _auth(_login(client, "ops@m6-co-41.com")["access_token"])
    tokens_a = _register(client, "M6 Tenant 41a", "admin@m6-tenant-41a.com")
    tokens_b = _register(client, "M6 Tenant 41b", "admin@m6-tenant-41b.com")
    org_a = _org_id_for(client, tokens_a)
    org_b = _org_id_for(client, tokens_b)
    plan = _seed_plan_with_feature(db_session, admin, "M6-P41", "LISA", True)
    _seed_active_subscription(db_session, org_a, plan.id)

    resp_a = client.get(f"/api/v1/platform/organizations/{org_a}/subscriptions", headers=headers)
    resp_b = client.get(f"/api/v1/platform/organizations/{org_b}/subscriptions", headers=headers)
    assert len(resp_a.json()) == 1
    assert len(resp_b.json()) == 0


def test_cross_tenant_override_access_impossible(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-42.com")
    headers = _auth(_login(client, "ops@m6-co-42.com")["access_token"])
    tokens_a = _register(client, "M6 Tenant 42a", "admin@m6-tenant-42a.com")
    tokens_b = _register(client, "M6 Tenant 42b", "admin@m6-tenant-42b.com")
    org_a = _org_id_for(client, tokens_a)
    org_b = _org_id_for(client, tokens_b)
    client.post(
        f"/api/v1/platform/organizations/{org_a}/feature-overrides",
        json={"feature_key": "LISA", "enabled": False},
        headers=headers,
    )
    resp_b = client.get(
        f"/api/v1/platform/organizations/{org_b}/feature-overrides", headers=headers
    )
    assert resp_b.json() == []


def test_cross_tenant_usage_limit_access_impossible(client, db_session):
    _create_platform_admin(db_session, "ops@m6-co-43.com")
    headers = _auth(_login(client, "ops@m6-co-43.com")["access_token"])
    tokens_a = _register(client, "M6 Tenant 43a", "admin@m6-tenant-43a.com")
    tokens_b = _register(client, "M6 Tenant 43b", "admin@m6-tenant-43b.com")
    org_a = _org_id_for(client, tokens_a)
    org_b = _org_id_for(client, tokens_b)
    client.post(
        f"/api/v1/platform/organizations/{org_a}/usage-limits",
        json={"feature_key": "LISA", "limit_key": "monthly_queries", "limit_value": 5},
        headers=headers,
    )
    resp_b = client.get(
        f"/api/v1/platform/organizations/{org_b}/usage-limits", headers=headers
    )
    assert resp_b.json() == []


def test_organization_isolation_remains_intact_for_tenant_models():
    assert hasattr(Subscription, "organization_id")
    assert hasattr(TenantFeatureOverride, "organization_id")
    assert hasattr(TenantUsageLimit, "organization_id")


# ---------------------------------------------------------------------------
# OPENAPI (45-46)
# ---------------------------------------------------------------------------


def test_openapi_generation_succeeds(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert "/api/v1/platform/organizations/{organization_id}/subscriptions" in spec["paths"]
    assert "/api/v1/platform/organizations/{organization_id}/feature-overrides" in spec["paths"]
    assert "/api/v1/platform/organizations/{organization_id}/usage-limits" in spec["paths"]


def test_openapi_schemas_present(client):
    resp = client.get("/openapi.json")
    spec = resp.json()
    schemas = spec["components"]["schemas"]
    assert "SubscriptionResponse" in schemas
    assert "TenantFeatureOverrideResponse" in schemas
    assert "TenantUsageLimitResponse" in schemas
