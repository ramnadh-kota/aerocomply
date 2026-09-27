"""Tests for admin-driven direct user creation and password reset:
POST /tenant/users, POST /tenant/users/{id}/reset-password,
POST /platform/organizations/{id}/users,
POST /platform/organizations/{id}/users/{id}/reset-password.

These bypass the OTP/self-service onboarding flow entirely -- the admin
chooses the password directly and relays it out-of-band -- so the tests
focus on: the new user can log in with the admin-chosen password, a reset
password takes effect (old password stops working), and RBAC/tenant
isolation are unchanged.
"""

from app.core.deps import get_db_session
from app.main import app


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


def test_tenant_admin_creates_user_with_direct_password_and_it_can_log_in(client):
    tokens = _register(client, "Direct Create Tenant", "admin@direct-create.com")
    resp = client.post(
        "/api/v1/tenant/users",
        json={
            "email": "staff@direct-create.com",
            "full_name": "Staff One",
            "role": "VIEWER",
            "password": "staffpassword123",
        },
        headers=_auth(tokens["access_token"]),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "staff@direct-create.com"
    assert body["roles"] == ["VIEWER"]
    assert body["is_active"] is True

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@direct-create.com", "password": "staffpassword123"},
    )
    assert login.status_code == 200


def test_tenant_admin_resets_user_password_and_old_password_stops_working(client):
    tokens = _register(client, "Reset Password Tenant", "admin@reset-pw.com")
    create = client.post(
        "/api/v1/tenant/users",
        json={
            "email": "staff@reset-pw.com",
            "full_name": "Staff Reset",
            "role": "VIEWER",
            "password": "originalpassword1",
        },
        headers=_auth(tokens["access_token"]),
    )
    user_id = create.json()["id"]

    reset = client.post(
        f"/api/v1/tenant/users/{user_id}/reset-password",
        json={"password": "brandnewpassword2"},
        headers=_auth(tokens["access_token"]),
    )
    assert reset.status_code == 200

    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@reset-pw.com", "password": "originalpassword1"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@reset-pw.com", "password": "brandnewpassword2"},
    )
    assert new_login.status_code == 200


def test_tenant_admin_cannot_create_user_with_platform_role(client):
    tokens = _register(client, "Forbidden Role Tenant", "admin@forbidden-role.com")
    resp = client.post(
        "/api/v1/tenant/users",
        json={
            "email": "sneaky@forbidden-role.com",
            "full_name": "Sneaky",
            "role": "PLATFORM_ADMIN",
            "password": "staffpassword123",
        },
        headers=_auth(tokens["access_token"]),
    )
    assert resp.status_code == 403


def test_platform_admin_creates_org_user_directly_and_resets_password(client):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)

    tokens = _register(client, "Platform Direct Create Org", "admin@platform-direct.com")
    org_id = client.get(
        "/api/v1/auth/me", headers=_auth(tokens["access_token"])
    ).json()["organization_id"]

    create = client.post(
        f"/api/v1/platform/organizations/{org_id}/users",
        json={
            "email": "staff@platform-direct.com",
            "full_name": "Platform Staff",
            "role": "VIEWER",
            "password": "platformstaffpass1",
        },
        headers=headers,
    )
    assert create.status_code == 201
    user_id = create.json()["id"]

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@platform-direct.com", "password": "platformstaffpass1"},
    )
    assert login.status_code == 200

    reset = client.post(
        f"/api/v1/platform/organizations/{org_id}/users/{user_id}/reset-password",
        json={"password": "platformnewpass2"},
        headers=headers,
    )
    assert reset.status_code == 200

    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@platform-direct.com", "password": "platformstaffpass1"},
    )
    assert old_login.status_code == 401


def test_tenant_admin_cannot_reset_password_of_user_in_other_organization(client):
    tokens_a = _register(client, "Isolation Tenant A", "admin@isolation-a.com")
    tokens_b = _register(client, "Isolation Tenant B", "admin@isolation-b.com")

    create_b = client.post(
        "/api/v1/tenant/users",
        json={
            "email": "staff@isolation-b.com",
            "full_name": "Staff B",
            "role": "VIEWER",
            "password": "staffpasswordb123",
        },
        headers=_auth(tokens_b["access_token"]),
    )
    user_b_id = create_b.json()["id"]

    resp = client.post(
        f"/api/v1/tenant/users/{user_b_id}/reset-password",
        json={"password": "hijackedpassword1"},
        headers=_auth(tokens_a["access_token"]),
    )
    assert resp.status_code == 404
