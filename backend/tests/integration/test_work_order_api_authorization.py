"""Phase 2 of the WorkOrder lifecycle feature: authorization-boundary tests
for the dedicated WORK_ORDER_READ/CREATE/UPDATE permissions that replaced
AIRCRAFT_READ/AIRCRAFT_WRITE on app/api/v1/work_orders.py's routes.

Mirrors the register/role-injection pattern in test_assessments_api.py
(register an org, then attach an additional User + UserRole row directly for
non-ORG_ADMIN roles) and the work-order entitlement fixture from
test_task_completion_api.py (require_feature("work_order_management") is a
separate, independent gate from RBAC and must be satisfied for every role
under test here).

This phase does not add a delete or restore endpoint, so WORK_ORDER_DELETE/
WORK_ORDER_RESTORE are exercised only at the permission-mapping level
(see tests/unit/test_permissions.py), not against a route.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole


def _register(client, org_name, email):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _entitle_work_orders(db_session, org_id):
    plan = Plan(name=f"WO-Auth-Plan-{org_id}", code=f"wo-auth-{org_id}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="work_order_management", enabled=True))
    db_session.add(
        Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=1),
            ends_at=None,
        )
    )
    db_session.commit()


def _login_as_role(client, db_session, org_id, role_name, email):
    """Create an additional user in the given org holding exactly one role,
    and return auth headers for it. Mirrors test_assessments_api.py's
    test_viewer_role_cannot_write_assessment fixture."""
    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name=f"{role_name} User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    db_session.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org_id))
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "supersecret123"}
    )
    assert login_resp.status_code == 200
    return _auth(login_resp.json()["access_token"])


def _setup_org_with_work_order(client, db_session, tag):
    """Register an org (ORG_ADMIN), entitle it for work_order_management,
    and create one aircraft + work order as a fixture other roles can read
    against. Returns (org_id, admin_auth, aircraft_id, work_order_id)."""
    tokens = _register(client, f"WO Auth {tag}", f"admin@wo-auth-{tag}.example.com")
    admin_auth = _auth(tokens["access_token"])
    org_id = uuid.UUID(
        client.get("/api/v1/auth/me", headers=admin_auth).json()["organization_id"]
    )
    _entitle_work_orders(db_session, org_id)

    aircraft_resp = client.post(
        "/api/v1/aircraft",
        json={"registration": f"N{tag}", "msn": f"MSN-{tag}", "aircraft_type": "B737"},
        headers=admin_auth,
    )
    assert aircraft_resp.status_code == 201
    aircraft_id = aircraft_resp.json()["id"]

    wo_resp = client.post(
        "/api/v1/work-orders",
        json={"aircraft_id": aircraft_id, "work_order_number": f"WO-{tag}-1"},
        headers=admin_auth,
    )
    assert wo_resp.status_code == 201
    work_order_id = wo_resp.json()["id"]

    return org_id, admin_auth, aircraft_id, work_order_id


class TestWorkOrderReadAuthorization:
    """GET /work-orders and GET /work-orders/{id}: WORK_ORDER_READ. Every
    tenant role in the approved mapping holds it."""

    def _assert_role_can_read(self, client, db_session, role_name, tag):
        org_id, admin_auth, _aircraft_id, work_order_id = _setup_org_with_work_order(
            client, db_session, tag
        )
        if role_name == "ORG_ADMIN":
            auth = admin_auth
        else:
            email = f"{role_name.lower()}@wo-auth-{tag}.example.com"
            auth = _login_as_role(client, db_session, org_id, role_name, email)

        list_resp = client.get("/api/v1/work-orders", headers=auth)
        assert list_resp.status_code == 200, list_resp.text

        get_resp = client.get(f"/api/v1/work-orders/{work_order_id}", headers=auth)
        assert get_resp.status_code == 200, get_resp.text

    def test_org_admin_can_read(self, client, db_session):
        self._assert_role_can_read(client, db_session, "ORG_ADMIN", "read-orgadmin")

    def test_camo_manager_can_read(self, client, db_session):
        self._assert_role_can_read(client, db_session, "CAMO_MANAGER", "read-camo")

    def test_maintenance_engineer_can_read(self, client, db_session):
        self._assert_role_can_read(client, db_session, "MAINTENANCE_ENGINEER", "read-maint")

    def test_quality_manager_can_read(self, client, db_session):
        self._assert_role_can_read(client, db_session, "QUALITY_MANAGER", "read-quality")

    def test_viewer_can_read(self, client, db_session):
        self._assert_role_can_read(client, db_session, "VIEWER", "read-viewer")


class TestWorkOrderCreateAuthorization:
    """POST /work-orders: WORK_ORDER_CREATE. VIEWER is denied."""

    def _create_as_role(self, client, db_session, role_name, tag):
        tokens = _register(client, f"WO Create {tag}", f"admin@wo-create-{tag}.example.com")
        admin_auth = _auth(tokens["access_token"])
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=admin_auth).json()["organization_id"]
        )
        _entitle_work_orders(db_session, org_id)

        aircraft_resp = client.post(
            "/api/v1/aircraft",
            json={"registration": f"N{tag}", "msn": f"MSN-{tag}", "aircraft_type": "B737"},
            headers=admin_auth,
        )
        assert aircraft_resp.status_code == 201
        aircraft_id = aircraft_resp.json()["id"]

        if role_name == "ORG_ADMIN":
            auth = admin_auth
        else:
            email = f"{role_name.lower()}@wo-create-{tag}.example.com"
            auth = _login_as_role(client, db_session, org_id, role_name, email)

        return client.post(
            "/api/v1/work-orders",
            json={"aircraft_id": aircraft_id, "work_order_number": f"WO-{tag}-1"},
            headers=auth,
        )

    def test_org_admin_can_create(self, client, db_session):
        resp = self._create_as_role(client, db_session, "ORG_ADMIN", "create-orgadmin")
        assert resp.status_code == 201, resp.text

    def test_camo_manager_can_create(self, client, db_session):
        resp = self._create_as_role(client, db_session, "CAMO_MANAGER", "create-camo")
        assert resp.status_code == 201, resp.text

    def test_maintenance_engineer_can_create(self, client, db_session):
        resp = self._create_as_role(client, db_session, "MAINTENANCE_ENGINEER", "create-maint")
        assert resp.status_code == 201, resp.text

    def test_quality_manager_can_create(self, client, db_session):
        resp = self._create_as_role(client, db_session, "QUALITY_MANAGER", "create-quality")
        assert resp.status_code == 201, resp.text

    def test_viewer_cannot_create(self, client, db_session):
        resp = self._create_as_role(client, db_session, "VIEWER", "create-viewer")
        assert resp.status_code == 403, resp.text


class TestWorkOrderUpdateAuthorization:
    """POST /work-orders/{id}/tasks and .../tasks/{task_id}/complete:
    WORK_ORDER_UPDATE. VIEWER is denied."""

    def _create_task_as_role(self, client, db_session, role_name, tag):
        org_id, admin_auth, _aircraft_id, work_order_id = _setup_org_with_work_order(
            client, db_session, tag
        )
        if role_name == "ORG_ADMIN":
            auth = admin_auth
        else:
            email = f"{role_name.lower()}@wo-update-{tag}.example.com"
            auth = _login_as_role(client, db_session, org_id, role_name, email)

        return client.post(
            f"/api/v1/work-orders/{work_order_id}/tasks",
            json={"work_order_id": work_order_id, "description": "Inspect fuselage"},
            headers=auth,
        )

    def test_org_admin_can_create_task(self, client, db_session):
        resp = self._create_task_as_role(client, db_session, "ORG_ADMIN", "update-orgadmin")
        assert resp.status_code == 201, resp.text

    def test_camo_manager_can_create_task(self, client, db_session):
        resp = self._create_task_as_role(client, db_session, "CAMO_MANAGER", "update-camo")
        assert resp.status_code == 201, resp.text

    def test_maintenance_engineer_can_create_task(self, client, db_session):
        resp = self._create_task_as_role(client, db_session, "MAINTENANCE_ENGINEER", "update-maint")
        assert resp.status_code == 201, resp.text

    def test_quality_manager_can_create_task(self, client, db_session):
        resp = self._create_task_as_role(client, db_session, "QUALITY_MANAGER", "update-quality")
        assert resp.status_code == 201, resp.text

    def test_viewer_cannot_create_task(self, client, db_session):
        resp = self._create_task_as_role(client, db_session, "VIEWER", "update-viewer")
        assert resp.status_code == 403, resp.text
