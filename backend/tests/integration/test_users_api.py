"""Tests for GET /users (the organization personnel directory backing the
Technician roster): tenant isolation, RBAC, and that reported roles are
real, not fabricated."""

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


def test_org_admin_sees_only_their_own_organization_users(client):
    tokens_a = _register(client, "Users Tenant A", "admin@users-tenant-a.com")
    tokens_b = _register(client, "Users Tenant B", "admin@users-tenant-b.com")

    resp_a = client.get("/api/v1/users", headers=_auth(tokens_a["access_token"]))
    assert resp_a.status_code == 200
    emails_a = {u["email"] for u in resp_a.json()}
    assert emails_a == {"admin@users-tenant-a.com"}

    resp_b = client.get("/api/v1/users", headers=_auth(tokens_b["access_token"]))
    assert resp_b.status_code == 200
    emails_b = {u["email"] for u in resp_b.json()}
    assert emails_b == {"admin@users-tenant-b.com"}


def test_registered_admin_has_org_admin_role_reported(client):
    tokens = _register(client, "Users Role Check", "admin@users-role-check.com")
    resp = client.get("/api/v1/users", headers=_auth(tokens["access_token"]))
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["roles"] == ["ORG_ADMIN"]
    assert users[0]["is_active"] is True


def test_platform_admin_gets_403_from_organization_users_endpoint(client, db_session):
    """PLATFORM_ADMIN is the one role that does NOT hold TECHNICIAN_READ —
    it must not gain implicit visibility into a customer organization's
    personnel just because it can manage tenants at the platform level."""
    org = Organization(name="Platform Ops For Users Test")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email="platform-users-test@kotas-aerospace.com",
        hashed_password=hash_password("supersecret123"),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "platform-users-test@kotas-aerospace.com", "password": "supersecret123"},
    )
    assert login.status_code == 200
    resp = client.get("/api/v1/users", headers=_auth(login.json()["access_token"]))
    assert resp.status_code == 403
