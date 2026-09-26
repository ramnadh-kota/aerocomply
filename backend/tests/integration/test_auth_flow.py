from app.core.security import hash_password
from app.models.organization import Organization
from app.models.user import User, UserRole


def test_register_login_me_roundtrip(client, platform_admin_headers):
    register_resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Test Airline",
            "admin_email": "admin@testairline.com",
            "admin_full_name": "Ada Admin",
            "admin_password": "supersecret123",
        },
        headers=platform_admin_headers,
    )
    assert register_resp.status_code == 201
    tokens = register_resp.json()
    assert "access_token" in tokens and "refresh_token" in tokens

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@testairline.com", "password": "supersecret123"},
    )
    assert login_resp.status_code == 200

    access_token = login_resp.json()["access_token"]
    me_resp = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["email"] == "admin@testairline.com"
    assert "ORG_ADMIN" in body["roles"]


def test_login_wrong_password_rejected(client, platform_admin_headers):
    client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Test Airline 2",
            "admin_email": "admin2@testairline.com",
            "admin_full_name": "Ada Admin",
            "admin_password": "supersecret123",
        },
        headers=platform_admin_headers,
    )
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin2@testairline.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


def test_me_requires_bearer_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_duplicate_organization_email_rejected(client, platform_admin_headers):
    payload = {
        "organization_name": "Dup Airline",
        "admin_email": "dup@testairline.com",
        "admin_full_name": "Dup Admin",
        "admin_password": "supersecret123",
    }
    first = client.post(
        "/api/v1/auth/register-organization", json=payload, headers=platform_admin_headers
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/auth/register-organization", json=payload, headers=platform_admin_headers
    )
    assert second.status_code == 409


# Phase 2 of the demo-access security work: POST /auth/register-organization
# is no longer a public/unauthenticated signup path -- it requires
# Permission.PLATFORM_MANAGE, exactly like /platform/organizations/provision.
def test_register_organization_requires_authentication(client):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Anonymous Airline",
            "admin_email": "anon@anonairline.com",
            "admin_full_name": "Anon Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 401


def test_register_organization_requires_platform_manage_permission(client, db_session):
    org = Organization(name="Ordinary Tenant Org")
    db_session.add(org)
    db_session.flush()
    tenant_user = User(
        organization_id=org.id,
        email="tenant-admin@ordinarytenant.com",
        hashed_password=hash_password("supersecret123"),
        full_name="Tenant Admin",
        is_active=True,
    )
    db_session.add(tenant_user)
    db_session.flush()
    db_session.add(UserRole(user_id=tenant_user.id, role_name="ORG_ADMIN", organization_id=org.id))
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": tenant_user.email, "password": "supersecret123"},
    )
    assert login_resp.status_code == 200
    tenant_token = login_resp.json()["access_token"]

    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Another Airline",
            "admin_email": "another@anotherairline.com",
            "admin_full_name": "Another Admin",
            "admin_password": "supersecret123",
        },
        headers={"Authorization": f"Bearer {tenant_token}"},
    )
    assert resp.status_code == 403


def test_register_organization_succeeds_for_platform_manage_caller(client, platform_admin_headers):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": "Authorized Bootstrap Airline",
            "admin_email": "admin@authorizedbootstrap.com",
            "admin_full_name": "Authorized Admin",
            "admin_password": "supersecret123",
        },
        headers=platform_admin_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body
