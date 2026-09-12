"""API-layer tests: a customer org admin must get 403 from /platform/*
endpoints (backend enforcement, never a frontend route check), and a
platform admin (created directly in the DB, since there is no public
self-registration path for platform staff) can manage organizations.
"""

from app.core.security import hash_password
from app.models.organization import Organization
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


def _create_platform_admin(db_session, email):
    org = Organization(name="KOTA'S AEROSPACE Platform Ops")
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


def test_customer_org_admin_gets_403_from_platform_endpoint(client):
    tokens = _register(client, "Platform Audit Customer", "admin@platform-audit-customer.com")
    resp = client.get("/api/v1/platform/organizations", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 403


def test_platform_admin_can_list_and_create_organizations(client, db_session):
    _create_platform_admin(db_session, "ops@kotas-aerospace-internal.com")

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ops@kotas-aerospace-internal.com", "password": "supersecret123"},
    )
    assert login.status_code == 200
    headers = _auth(login.json()["access_token"])

    create_resp = client.post(
        "/api/v1/platform/organizations", json={"name": "New Customer MRO"}, headers=headers
    )
    assert create_resp.status_code == 201
    org_id = create_resp.json()["id"]

    list_resp = client.get("/api/v1/platform/organizations", headers=headers)
    assert list_resp.status_code == 200
    assert any(o["id"] == org_id for o in list_resp.json())

    suspend_resp = client.post(f"/api/v1/platform/organizations/{org_id}/suspend", headers=headers)
    assert suspend_resp.status_code == 200
    assert suspend_resp.json()["status"] == "SUSPENDED"


def test_platform_admin_can_bootstrap_org_admin_for_new_tenant(client, db_session):
    _create_platform_admin(db_session, "ops2@kotas-aerospace-internal.com")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ops2@kotas-aerospace-internal.com", "password": "supersecret123"},
    )
    headers = _auth(login.json()["access_token"])

    create_resp = client.post(
        "/api/v1/platform/organizations", json={"name": "Onboard Me MRO"}, headers=headers
    )
    org_id = create_resp.json()["id"]

    admin_resp = client.post(
        f"/api/v1/platform/organizations/{org_id}/admins",
        json={
            "email": "admin@onboard-me.com",
            "full_name": "Onboard Admin",
            "password": "supersecret123",
        },
        headers=headers,
    )
    assert admin_resp.status_code == 201

    customer_login = client.post(
        "/api/v1/auth/login", json={"email": "admin@onboard-me.com", "password": "supersecret123"}
    )
    assert customer_login.status_code == 200


def test_suspended_organization_user_cannot_log_in_via_api(client, db_session):
    _create_platform_admin(db_session, "ops3@kotas-aerospace-internal.com")
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ops3@kotas-aerospace-internal.com", "password": "supersecret123"},
    )
    headers = _auth(login.json()["access_token"])

    org_resp = client.post(
        "/api/v1/platform/organizations", json={"name": "Will Be Suspended MRO"}, headers=headers
    )
    org_id = org_resp.json()["id"]
    client.post(
        f"/api/v1/platform/organizations/{org_id}/admins",
        json={
            "email": "admin@will-be-suspended.com",
            "full_name": "Admin",
            "password": "supersecret123",
        },
        headers=headers,
    )
    client.post(f"/api/v1/platform/organizations/{org_id}/suspend", headers=headers)

    blocked_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@will-be-suspended.com", "password": "supersecret123"},
    )
    assert blocked_login.status_code == 401
