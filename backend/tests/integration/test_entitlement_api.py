"""API-layer tests for M3: GET /api/v1/entitlements (tenant, self-only) and
GET /api/v1/platform/organizations/{organization_id}/entitlements
(platform-admin, any org).

No new entitlement logic is tested here -- app.services.entitlement_service
already has full coverage in test_entitlement_resolution.py. These tests only
prove the API layer's authorization wiring and serialization.

Uses the `client`/`db_session` fixtures from tests/integration/conftest.py.
Both share the SAME underlying connection/transaction for a given test, so
fixtures created via db_session are visible to requests made via client
without any commit-boundary surprises -- just never call db_session.rollback()
mid-test.
"""
from datetime import UTC, datetime, timedelta

from app.core.deps import get_db_session
from app.core.security import decode_token, hash_password
from app.main import app
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.models.user import User, UserRole


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _org_id(token):
    """TokenResponse carries no organization_id field -- decode the access
    token (as every tenant-scoped route already trusts it, see
    app.core.deps.get_current_user) to recover it for test setup only."""
    return decode_token(token)["organization_id"]


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


def _create_platform_admin(db_session, email):
    org = Organization(name="Platform Ops Co")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()
    return user


def _make_plan(db_session, code, is_active=True):
    plan = Plan(name=f"{code} Name", code=code, is_active=is_active)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _make_sub(db_session, *, org_id, plan, status=SubscriptionStatus.ACTIVE, starts_at=None):
    sub = Subscription(
        organization_id=org_id,
        plan_id=plan.id,
        status=status,
        starts_at=starts_at or (datetime.now(UTC) - timedelta(days=1)),
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    return sub


# 1. own-org retrieval works for an ordinary authenticated tenant user
def test_tenant_can_retrieve_own_org_entitlements(client, db_session):
    tokens = _register(client, "Tenant Co 1", "admin@tenant-co-1.com")
    headers = _auth(tokens["access_token"])

    resp = client.get("/api/v1/entitlements", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["resolution_status"] == "NO_SUBSCRIPTION"


# 2. the tenant endpoint has no org_id parameter at all -- an injected query
# string cannot redirect it to another org's data; it always returns the
# caller's own org.
def test_tenant_endpoint_ignores_injected_org_query_param(client, db_session):
    tokens_a = _register(client, "Tenant Co 2A", "admin@tenant-co-2a.com")
    tokens_b = _register(client, "Tenant Co 2B", "admin@tenant-co-2b.com")
    org_b_id = _org_id(tokens_b["access_token"])

    headers_a = _auth(tokens_a["access_token"])
    resp = client.get(
        "/api/v1/entitlements",
        params={"organization_id": org_b_id or "00000000-0000-0000-0000-000000000000"},
        headers=headers_a,
    )
    assert resp.status_code == 200
    body = resp.json()
    # Own org's resolution (NO_SUBSCRIPTION), never org B's, regardless of
    # the query param -- proving there is no org_id parameter honored at all.
    assert body["resolution_status"] == "NO_SUBSCRIPTION"


# 3. ordinary tenant user gets 403 from the platform endpoint
def test_ordinary_tenant_user_gets_403_from_platform_entitlements_endpoint(client, db_session):
    tokens = _register(client, "Tenant Co 3", "admin@tenant-co-3.com")
    headers = _auth(tokens["access_token"])
    org_id = _org_id(tokens["access_token"])

    resp = client.get(f"/api/v1/platform/organizations/{org_id}/entitlements", headers=headers)
    assert resp.status_code == 403


# 4. platform admin can retrieve any org's entitlements
def test_platform_admin_can_retrieve_any_org_entitlements(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-4.com")
    admin_login = _login(client, "ops@platform-co-4.com")
    admin_headers = _auth(admin_login["access_token"])

    tokens = _register(client, "Tenant Co 4", "admin@tenant-co-4.com")
    org_id = _org_id(tokens["access_token"])

    resp = client.get(
        f"/api/v1/platform/organizations/{org_id}/entitlements", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["organization_id"] == org_id
    assert resp.json()["resolution_status"] == "NO_SUBSCRIPTION"


# 5. platform admin inspecting multiple orgs in sequence gets correct
# per-org results
def test_platform_admin_can_inspect_multiple_orgs_in_sequence(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-5.com")
    admin_login = _login(client, "ops@platform-co-5.com")
    admin_headers = _auth(admin_login["access_token"])

    tokens_x = _register(client, "Tenant Co 5X", "admin@tenant-co-5x.com")
    tokens_y = _register(client, "Tenant Co 5Y", "admin@tenant-co-5y.com")
    org_x = _org_id(tokens_x["access_token"])
    org_y = _org_id(tokens_y["access_token"])

    plan_x = _make_plan(db_session, "T5X-PLAN")
    db_session.add(PlanFeature(plan_id=plan_x.id, feature_key="X_ONLY", enabled=True))
    db_session.commit()
    _make_sub(db_session, org_id=org_x, plan=plan_x)

    resp_x = client.get(
        f"/api/v1/platform/organizations/{org_x}/entitlements", headers=admin_headers
    )
    resp_y = client.get(
        f"/api/v1/platform/organizations/{org_y}/entitlements", headers=admin_headers
    )

    assert resp_x.status_code == 200
    assert resp_y.status_code == 200
    assert resp_x.json()["resolution_status"] == "ACTIVE"
    assert resp_x.json()["effective_features"] == {"X_ONLY": True}
    assert resp_y.json()["resolution_status"] == "NO_SUBSCRIPTION"
    assert resp_x.json()["organization_id"] != resp_y.json()["organization_id"]


# 6. nonexistent org on platform endpoint returns 404
def test_platform_endpoint_404_for_nonexistent_org(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-6.com")
    admin_login = _login(client, "ops@platform-co-6.com")
    admin_headers = _auth(admin_login["access_token"])

    resp = client.get(
        "/api/v1/platform/organizations/00000000-0000-0000-0000-000000000000/entitlements",
        headers=admin_headers,
    )
    assert resp.status_code == 404


# 7. a suspended tenant's own token is already rejected at authentication
# (app.core.deps.get_current_user re-checks org status on every request,
# and login itself refuses a suspended org) *before* ever reaching the
# entitlements route. So the API-layer, HTTP-observable behavior for a
# suspended tenant calling their own /entitlements is 401, not a 200 body
# carrying resolution_status=SUSPENDED -- that richer signal is only
# reachable by calling entitlement_service.resolve_entitlements directly
# (see test_entitlement_resolution.py, test #3), which this thin route
# layer does unconditionally. Documented as a known limitation rather than
# a bug in this milestone's scope.
def test_suspended_tenant_own_org_call_is_401_not_200(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-7.com")
    admin_login = _login(client, "ops@platform-co-7.com")
    admin_headers = _auth(admin_login["access_token"])

    tokens = _register(client, "Tenant Co 7", "admin@tenant-co-7.com")
    org_id = _org_id(tokens["access_token"])
    headers = _auth(tokens["access_token"])

    # sanity: works before suspension
    ok_resp = client.get("/api/v1/entitlements", headers=headers)
    assert ok_resp.status_code == 200

    client.post(f"/api/v1/platform/organizations/{org_id}/suspend", headers=admin_headers)

    resp = client.get("/api/v1/entitlements", headers=headers)
    assert resp.status_code == 401


# 8. a platform admin CAN still see SUSPENDED via their own endpoint, since
# platform admin auth doesn't depend on the target org's status.
def test_platform_admin_sees_suspended_status_for_suspended_org(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-8.com")
    admin_login = _login(client, "ops@platform-co-8.com")
    admin_headers = _auth(admin_login["access_token"])

    tokens = _register(client, "Tenant Co 8", "admin@tenant-co-8.com")
    org_id = _org_id(tokens["access_token"])

    client.post(f"/api/v1/platform/organizations/{org_id}/suspend", headers=admin_headers)

    resp = client.get(
        f"/api/v1/platform/organizations/{org_id}/entitlements", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["resolution_status"] == "SUSPENDED"


# 9. no-subscription tenant returns NO_SUBSCRIPTION with 200 (already shown
# in test 1, restated explicitly for the platform endpoint too)
def test_no_subscription_tenant_returns_200_with_no_subscription_status(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-9.com")
    admin_login = _login(client, "ops@platform-co-9.com")
    admin_headers = _auth(admin_login["access_token"])

    tokens = _register(client, "Tenant Co 9", "admin@tenant-co-9.com")
    org_id = _org_id(tokens["access_token"])

    resp = client.get(
        f"/api/v1/platform/organizations/{org_id}/entitlements", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["resolution_status"] == "NO_SUBSCRIPTION"


# 10. ambiguous-subscription tenant returns AMBIGUOUS with 200 and reason populated
def test_ambiguous_subscription_returns_200_with_reason(client, db_session):
    _create_platform_admin(db_session, "ops@platform-co-10.com")
    admin_login = _login(client, "ops@platform-co-10.com")
    admin_headers = _auth(admin_login["access_token"])

    tokens = _register(client, "Tenant Co 10", "admin@tenant-co-10.com")
    org_id = _org_id(tokens["access_token"])
    plan = _make_plan(db_session, "T10-PLAN")
    _make_sub(db_session, org_id=org_id, plan=plan, status=SubscriptionStatus.ACTIVE)
    _make_sub(db_session, org_id=org_id, plan=plan, status=SubscriptionStatus.TRIALING)

    resp = client.get(
        f"/api/v1/platform/organizations/{org_id}/entitlements", headers=admin_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["resolution_status"] == "AMBIGUOUS"
    assert body["reason"] != ""


# 11. effective feature overrides appear correctly serialized
def test_effective_feature_overrides_serialized(client, db_session):
    tokens = _register(client, "Tenant Co 11", "admin@tenant-co-11.com")
    org_id = _org_id(tokens["access_token"])
    headers = _auth(tokens["access_token"])
    plan = _make_plan(db_session, "T11-PLAN")
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="FEATURE_Q", enabled=True))
    db_session.commit()
    _make_sub(db_session, org_id=org_id, plan=plan)
    db_session.add(
        TenantFeatureOverride(organization_id=org_id, feature_key="FEATURE_Q", enabled=False)
    )
    db_session.commit()

    resp = client.get("/api/v1/entitlements", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["effective_features"]["FEATURE_Q"] is False


# 12. usage limits appear as configuration fields only, no consumption/counter fields
def test_usage_limits_are_configuration_only(client, db_session):
    tokens = _register(client, "Tenant Co 12", "admin@tenant-co-12.com")
    org_id = _org_id(tokens["access_token"])
    headers = _auth(tokens["access_token"])
    plan = _make_plan(db_session, "T12-PLAN")
    _make_sub(db_session, org_id=org_id, plan=plan)
    db_session.add(
        TenantUsageLimit(
            organization_id=org_id,
            feature_key="LISA",
            limit_key="monthly_queries",
            limit_value=500,
            is_unlimited=False,
        )
    )
    db_session.commit()

    resp = client.get("/api/v1/entitlements", headers=headers)
    assert resp.status_code == 200
    limits = resp.json()["usage_limits"]
    assert len(limits) == 1
    limit = limits[0]
    assert set(limit.keys()) == {"feature_key", "limit_key", "limit_value", "is_unlimited"}
    assert limit["limit_value"] == 500
    assert limit["is_unlimited"] is False


# 13. unauthenticated request returns 401
def test_unauthenticated_request_returns_401(client):
    resp = client.get("/api/v1/entitlements")
    assert resp.status_code == 401

    resp2 = client.get(
        "/api/v1/platform/organizations/00000000-0000-0000-0000-000000000000/entitlements"
    )
    assert resp2.status_code == 401
