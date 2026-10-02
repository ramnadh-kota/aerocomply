"""Tiered tenant dashboard/usage/profile visibility.

Every authenticated tenant user keeps operational/fleet counts. Commercial
details (plan code, subscription status, entitlement count, usage limits),
seat/invitation figures and primary-contact details require org:manage. The
restriction is enforced by the API (response shape / 403), not just the UI.
"""

import uuid

from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
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
            "admin_full_name": "Admin Person",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _user_with_role(client, db_session, org_id, email, role):
    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name=f"{role} User",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name=role, organization_id=org_id))
    db_session.commit()
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    assert resp.status_code == 200
    return _auth(resp.json()["access_token"])


def _setup(client, db_session, suffix):
    admin_email = f"admin@tier-{suffix}.com"
    tokens = _register(client, f"Tier {suffix}", admin_email)
    admin = _auth(tokens["access_token"])
    org_id = uuid.UUID(client.get("/api/v1/auth/me", headers=admin).json()["organization_id"])
    return admin_email, admin, org_id


RESTRICTED_DASHBOARD_FIELDS = (
    "users_count",
    "active_users_count",
    "pending_invitations_count",
    "current_plan",
    "subscription_status",
    "effective_features_count",
)
FLEET_FIELDS = ("fleet_count", "aircraft_count", "drone_count", "facility_count", "team_count")


def test_admin_sees_full_dashboard_and_usage(client, db_session):
    admin_email, admin, org_id = _setup(client, db_session, "a1")
    d = client.get("/api/v1/tenant/dashboard", headers=admin).json()
    assert d["restricted"] is False
    assert d["users_count"] >= 1 and d["active_users_count"] >= 1
    assert d["pending_invitations_count"] is not None
    assert d["effective_features_count"] is not None
    assert d["organization"]["primary_contact_email"] == admin_email
    assert client.get("/api/v1/tenant/usage", headers=admin).status_code == 200
    assert client.get("/api/v1/tenant/profile", headers=admin).json()["primary_contact_email"] == admin_email


def test_viewer_dashboard_withholds_restricted_fields_but_keeps_fleet_counts(client, db_session):
    admin_email, _admin, org_id = _setup(client, db_session, "v1")
    viewer = _user_with_role(client, db_session, org_id, "viewer@tier-v1.com", "VIEWER")

    resp = client.get("/api/v1/tenant/dashboard", headers=viewer)
    assert resp.status_code == 200
    d = resp.json()
    assert d["restricted"] is True
    for f in RESTRICTED_DASHBOARD_FIELDS:
        assert d[f] is None, f
    for f in FLEET_FIELDS:
        assert isinstance(d[f], int), f
    assert d["organization"]["name"] == "Tier v1"
    assert d["organization"]["primary_contact_email"] is None
    assert d["organization"]["primary_contact_name"] is None
    # No sensitive value leaks anywhere in the serialized body.
    assert admin_email not in resp.text
    assert all(a["category"] != "PEOPLE" for a in d["attention_items"])


def test_viewer_cannot_read_usage_or_contact_via_profile(client, db_session):
    admin_email, _admin, org_id = _setup(client, db_session, "v2")
    viewer = _user_with_role(client, db_session, org_id, "viewer@tier-v2.com", "VIEWER")
    assert client.get("/api/v1/tenant/usage", headers=viewer).status_code == 403
    prof = client.get("/api/v1/tenant/profile", headers=viewer)
    assert prof.status_code == 200
    assert prof.json()["primary_contact_email"] is None
    assert prof.json()["primary_contact_name"] is None
    assert admin_email not in prof.text
    # Existing admin-only tenant endpoints stay admin-only.
    assert client.get("/api/v1/tenant/users", headers=viewer).status_code == 403


def test_non_manager_operational_roles_are_also_restricted(client, db_session):
    _e, _admin, org_id = _setup(client, db_session, "m1")
    eng = _user_with_role(client, db_session, org_id, "eng@tier-m1.com", "MAINTENANCE_ENGINEER")
    assert client.get("/api/v1/tenant/dashboard", headers=eng).json()["restricted"] is True
    assert client.get("/api/v1/tenant/usage", headers=eng).status_code == 403


def test_tiered_responses_are_tenant_scoped(client, db_session):
    email_a, admin_a, org_a = _setup(client, db_session, "x1")
    email_b, admin_b, org_b = _setup(client, db_session, "x2")
    viewer_a = _user_with_role(client, db_session, org_a, "viewer@tier-x1.com", "VIEWER")

    for headers in (viewer_a, admin_a):
        d = client.get("/api/v1/tenant/dashboard", headers=headers)
        assert d.json()["organization"]["id"] == str(org_a)
        assert str(org_b) not in d.text and email_b not in d.text and "Tier x2" not in d.text
    usage = client.get("/api/v1/tenant/usage", headers=admin_a)
    assert usage.json()["organization_id"] == str(org_a)
    assert str(org_b) not in usage.text
    # And the other tenant's admin sees only their own org.
    assert client.get("/api/v1/tenant/dashboard", headers=admin_b).json()["organization"]["id"] == str(org_b)


def test_tenant_endpoints_require_authentication(client):
    for path in ("/api/v1/tenant/dashboard", "/api/v1/tenant/usage", "/api/v1/tenant/profile"):
        assert client.get(path).status_code in (401, 403)
