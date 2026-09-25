"""M21.5: real HTTP-level proof that require_feature (app/core/deps.py,
built in M17.3, previously wired nowhere) is now actually enforced at the
API boundary for the three real feature-gated GET endpoints this round
protected:

  - GET /api/v1/work-orders, GET /api/v1/work-orders/{id}
    (feature_key="work_order_management")
  - GET /api/v1/drones, GET /api/v1/drones/{id}
    (feature_key="drone_fleet_management")
  - GET /api/v1/procurement-requests, GET /api/v1/procurement-requests/{id}
    (feature_key="procurement_management")

Unlike tests/integration/test_require_feature_dependency.py (which calls the
dependency factory's inner function directly, proving the resolver logic in
isolation), this file drives real HTTP requests through the real FastAPI app
via the `client` fixture, proving the dependency is actually mounted on the
real routes -- the exact gap M21.4's report flagged as unbuilt ("No
require_feature() backend dependency was added anywhere").
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride
from app.models.user import User, UserRole


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


def _org_id(client, token) -> uuid.UUID:
    return uuid.UUID(client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"])


def _add_role_user(db_session, org_id, email, role_name):
    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Role User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org_id))
    db_session.commit()
    return user


def _make_plan(db_session, *, code, feature_key, enabled=True):
    plan = Plan(name=code, code=code, is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key=feature_key, enabled=enabled))
    db_session.commit()
    return plan


def _subscribe(db_session, *, org_id, plan, status=SubscriptionStatus.ACTIVE, ends_at=None):
    sub = Subscription(
        organization_id=org_id,
        plan_id=plan.id,
        status=status,
        starts_at=datetime.now(UTC) - timedelta(days=1),
        ends_at=ends_at,
    )
    db_session.add(sub)
    db_session.commit()
    return sub


FEATURE_ENDPOINTS = [
    ("work_order_management", "/api/v1/work-orders"),
    ("drone_fleet_management", "/api/v1/drones"),
    ("procurement_management", "/api/v1/procurement-requests"),
]


class TestEntitledOrgSucceeds:
    def test_all_three_features_succeed_when_entitled(self, client, db_session):
        for feature_key, url in FEATURE_ENDPOINTS:
            org = _register(client, f"Entitled Org {feature_key}", f"admin-{feature_key}@example.com")
            token = _login(client, f"admin-{feature_key}@example.com")["access_token"]
            org_id = _org_id(client, token)
            plan = _make_plan(db_session, code=f"PLAN-{feature_key}", feature_key=feature_key, enabled=True)
            _subscribe(db_session, org_id=org_id, plan=plan)

            resp = client.get(url, headers=_auth(token))
            assert resp.status_code == 200, f"{feature_key}: expected 200, got {resp.status_code}: {resp.text}"


class TestUnentitledOrgDenied:
    def test_no_subscription_gets_403_with_stable_code(self, client, db_session):
        org = _register(client, "Unentitled Org WO", "unent-wo@example.com")
        token = _login(client, "unent-wo@example.com")["access_token"]

        resp = client.get("/api/v1/work-orders", headers=_auth(token))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"

    def test_feature_disabled_on_plan_gets_403(self, client, db_session):
        org = _register(client, "Unentitled Org Drone", "unent-drone@example.com")
        token = _login(client, "unent-drone@example.com")["access_token"]
        org_id = _org_id(client, token)
        plan = _make_plan(db_session, code="PLAN-NO-DRONE", feature_key="drone_fleet_management", enabled=False)
        _subscribe(db_session, org_id=org_id, plan=plan)

        resp = client.get("/api/v1/drones", headers=_auth(token))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"

    def test_org_admin_broad_rbac_still_denied_if_unentitled(self, client, db_session):
        # ORG_ADMIN has broad RBAC permissions (including PROCUREMENT_READ)
        # but that must not substitute for entitlement.
        org = _register(client, "Unentitled Org Procurement", "unent-proc@example.com")
        token = _login(client, "unent-proc@example.com")["access_token"]

        resp = client.get("/api/v1/procurement-requests", headers=_auth(token))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"


class TestRbacIndependentlyStillEnforced:
    def test_entitled_but_lacking_rbac_permission_denied_for_different_reason(self, client, db_session):
        # A user with no role grant at all (every real role in
        # app/core/permissions.py's ROLE_PERMISSIONS -- VIEWER included --
        # holds PROCUREMENT_READ, so a roleless user is the genuine
        # "RBAC denies, entitlement would have allowed" case) lacks
        # PROCUREMENT_READ even though the org IS entitled -- proves RBAC
        # denial still independently works and isn't bypassed by
        # entitlement being satisfied.
        org = _register(client, "Entitled Org Roleless", "roleless-proc@example.com")
        admin_token = _login(client, "roleless-proc@example.com")["access_token"]
        org_id = _org_id(client, admin_token)
        plan = _make_plan(db_session, code="PLAN-ROLELESS-PROC", feature_key="procurement_management", enabled=True)
        _subscribe(db_session, org_id=org_id, plan=plan)

        # Deliberately no UserRole row -> permissions_for_roles([]) is empty,
        # so PROCUREMENT_READ is genuinely absent.
        roleless_user = User(
            organization_id=org_id,
            email="roleless-only@example.com",
            hashed_password=hash_password("supersecret123"),
            full_name="Roleless User",
            is_active=True,
        )
        db_session.add(roleless_user)
        db_session.commit()
        roleless_token = _login(client, "roleless-only@example.com")["access_token"]

        resp = client.get("/api/v1/procurement-requests", headers=_auth(roleless_token))
        assert resp.status_code == 403
        # Confirm it's the RBAC gate, not entitlement, that fired: an
        # entitled-but-authorized admin succeeds on the identical org.
        admin_resp = client.get("/api/v1/procurement-requests", headers=_auth(admin_token))
        assert admin_resp.status_code == 200


class TestTenantIsolation:
    def test_org_b_entitlement_never_leaks_into_org_a_check(self, client, db_session):
        _register(client, "Isolation Org A", "iso-a@example.com")
        _register(client, "Isolation Org B", "iso-b@example.com")
        token_a = _login(client, "iso-a@example.com")["access_token"]
        token_b = _login(client, "iso-b@example.com")["access_token"]
        org_b_id = _org_id(client, token_b)

        plan_b = _make_plan(db_session, code="PLAN-ISO-B", feature_key="drone_fleet_management", enabled=True)
        _subscribe(db_session, org_id=org_b_id, plan=plan_b)
        # Org A has no subscription at all.

        resp = client.get("/api/v1/drones", headers=_auth(token_a))
        assert resp.status_code == 403


class TestTenantFeatureOverridePrecedence:
    def test_override_grants_feature_plan_does_not_include(self, client, db_session):
        org = _register(client, "Override Grant Org", "override-grant@example.com")
        token = _login(client, "override-grant@example.com")["access_token"]
        org_id = _org_id(client, token)
        plan = _make_plan(db_session, code="PLAN-OVERRIDE-GRANT", feature_key="drone_fleet_management", enabled=False)
        _subscribe(db_session, org_id=org_id, plan=plan)

        # Without override: denied.
        assert client.get("/api/v1/drones", headers=_auth(token)).status_code == 403

        db_session.add(
            TenantFeatureOverride(
                organization_id=org_id,
                feature_key="drone_fleet_management",
                enabled=True,
                reason="Pilot trial grant",
            )
        )
        db_session.commit()

        assert client.get("/api/v1/drones", headers=_auth(token)).status_code == 200

    def test_override_revokes_feature_plan_includes(self, client, db_session):
        org = _register(client, "Override Revoke Org", "override-revoke@example.com")
        token = _login(client, "override-revoke@example.com")["access_token"]
        org_id = _org_id(client, token)
        plan = _make_plan(
            db_session, code="PLAN-OVERRIDE-REVOKE", feature_key="procurement_management", enabled=True
        )
        _subscribe(db_session, org_id=org_id, plan=plan)

        assert client.get("/api/v1/procurement-requests", headers=_auth(token)).status_code == 200

        db_session.add(
            TenantFeatureOverride(
                organization_id=org_id,
                feature_key="procurement_management",
                enabled=False,
                reason="Revoked for billing dispute",
            )
        )
        db_session.commit()

        assert client.get("/api/v1/procurement-requests", headers=_auth(token)).status_code == 403


class TestSubscriptionStateBehavior:
    def test_expired_subscription_denies(self, client, db_session):
        org = _register(client, "Expired Sub Org", "expired-sub@example.com")
        token = _login(client, "expired-sub@example.com")["access_token"]
        org_id = _org_id(client, token)
        plan = _make_plan(db_session, code="PLAN-EXPIRED", feature_key="work_order_management", enabled=True)
        _subscribe(
            db_session,
            org_id=org_id,
            plan=plan,
            ends_at=datetime.now(UTC) - timedelta(hours=1),
        )

        resp = client.get("/api/v1/work-orders", headers=_auth(token))
        assert resp.status_code == 403

    def test_suspended_organization_denies_even_with_active_entitled_plan(self, client, db_session):
        from app.models.organization import Organization, OrganizationStatus

        org = _register(client, "Suspend Org", "suspend-org@example.com")
        token = _login(client, "suspend-org@example.com")["access_token"]
        org_id = _org_id(client, token)
        plan = _make_plan(db_session, code="PLAN-SUSPEND", feature_key="drone_fleet_management", enabled=True)
        _subscribe(db_session, org_id=org_id, plan=plan)

        assert client.get("/api/v1/drones", headers=_auth(token)).status_code == 200

        org_row = db_session.get(Organization, org_id)
        org_row.status = OrganizationStatus.SUSPENDED
        db_session.commit()

        # A suspended org's token is now rejected at get_current_user
        # (401, pre-existing behavior) -- entitlement never even gets
        # evaluated, which is the documented fail-fast order.
        resp = client.get("/api/v1/drones", headers=_auth(token))
        assert resp.status_code == 401


class TestPlatformAdminUnaffected:
    def test_platform_route_works_regardless_of_any_subscription_state(self, client, db_session):
        from app.core.security import create_access_token
        from app.models.organization import Organization

        platform_org = Organization(name="Platform Operations Test")
        db_session.add(platform_org)
        db_session.flush()
        admin = User(
            organization_id=platform_org.id,
            email="platform-admin-m215@example.com",
            hashed_password=hash_password("supersecret123"),
            full_name="Platform Admin",
            is_active=True,
        )
        db_session.add(admin)
        db_session.flush()
        db_session.add(
            UserRole(user_id=admin.id, role_name="PLATFORM_ADMIN", organization_id=platform_org.id)
        )
        db_session.commit()

        token = create_access_token(
            user_id=admin.id,
            organization_id=platform_org.id,
            roles=["PLATFORM_ADMIN"],
            email=admin.email,
            full_name=admin.full_name,
            email_verified=True,
        )

        # Platform Operations org has no Plan/Subscription at all -- if
        # require_feature were (incorrectly) applied to platform routes,
        # this would 403. It is not applied, so this must succeed (subject
        # only to PLATFORM_MANAGE, which PLATFORM_ADMIN holds).
        resp = client.get("/api/v1/platform/organizations", headers=_auth(token))
        assert resp.status_code == 200
