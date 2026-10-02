"""PATCH /platform/organizations/{org}/users/{user}: Platform Admin edits of tenant users.

Covers persistence, audit, tenant-role-only restriction (no platform-role escalation), the last-ORG_ADMIN guard,
email uniqueness, cross-tenant isolation and that tenant users cannot call the endpoint."""

from sqlalchemy import select

from app.models.audit_event import AuditEvent
from tests.integration.test_admin_direct_user_management import _auth, _register


def _create_user(client, token, email, role="VIEWER"):
    resp = client.post(
        "/api/v1/tenant/users",
        json={"email": email, "full_name": "Staff", "role": role, "password": "staffpassword123"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _org_id(client, token):
    return client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]


def test_platform_admin_edits_name_email_role_and_status(client, platform_admin_headers, db_session):
    tokens = _register(client, "Edit Users Org", "admin@edit-users.com")
    org = _org_id(client, tokens["access_token"])
    uid = _create_user(client, tokens["access_token"], "staff@edit-users.com")

    resp = client.patch(
        f"/api/v1/platform/organizations/{org}/users/{uid}",
        json={"full_name": "Renamed Staff", "email": "renamed@edit-users.com", "roles": ["CAMO_MANAGER"], "is_active": False},
        headers=platform_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["full_name"], body["email"], body["roles"], body["is_active"]) == (
        "Renamed Staff", "renamed@edit-users.com", ["CAMO_MANAGER"], False,
    )

    listed = client.get(f"/api/v1/platform/organizations/{org}/users", headers=platform_admin_headers).json()
    assert any(u["id"] == uid and u["email"] == "renamed@edit-users.com" for u in listed)

    actions = set(db_session.execute(select(AuditEvent.action).where(AuditEvent.entity_id == uid)).scalars())
    assert {"platform.organization.user_updated", "tenant.user.roles_updated", "tenant.user.status_updated"} <= actions


def test_platform_roles_cannot_be_assigned_and_empty_patch_rejected(client, platform_admin_headers):
    tokens = _register(client, "Escalation Org", "admin@escalate.com")
    org = _org_id(client, tokens["access_token"])
    uid = _create_user(client, tokens["access_token"], "staff@escalate.com")
    url = f"/api/v1/platform/organizations/{org}/users/{uid}"
    assert client.patch(url, json={"roles": ["PLATFORM_ADMIN"]}, headers=platform_admin_headers).status_code == 409
    assert client.patch(url, json={}, headers=platform_admin_headers).status_code == 409


def test_last_org_admin_cannot_be_demoted_or_email_duplicated(client, platform_admin_headers):
    tokens = _register(client, "Last Admin Org", "admin@last-admin.com")
    org = _org_id(client, tokens["access_token"])
    admin_id = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()["id"]
    other = _create_user(client, tokens["access_token"], "dup@last-admin.com")

    assert client.patch(
        f"/api/v1/platform/organizations/{org}/users/{admin_id}", json={"roles": ["VIEWER"]}, headers=platform_admin_headers
    ).status_code == 409
    assert client.patch(
        f"/api/v1/platform/organizations/{org}/users/{other}", json={"email": "ADMIN@last-admin.com"}, headers=platform_admin_headers
    ).status_code == 409


def test_cross_tenant_and_tenant_caller_are_rejected(client, platform_admin_headers):
    a = _register(client, "Tenant A Edit", "admin@tenant-a-edit.com")
    b = _register(client, "Tenant B Edit", "admin@tenant-b-edit.com")
    org_a, org_b = _org_id(client, a["access_token"]), _org_id(client, b["access_token"])
    user_b = _create_user(client, b["access_token"], "staff@tenant-b-edit.com")

    # user belongs to B but addressed through A's org id -> 404, nothing changed
    assert client.patch(
        f"/api/v1/platform/organizations/{org_a}/users/{user_b}", json={"full_name": "X"}, headers=platform_admin_headers
    ).status_code == 404
    # tenant admin may not use the platform endpoint at all
    assert client.patch(
        f"/api/v1/platform/organizations/{org_b}/users/{user_b}", json={"full_name": "X"}, headers=_auth(b["access_token"])
    ).status_code == 403


def test_tenant_user_directory_requires_user_manage(client):
    """Personnel directory (names/emails/roles) is admin data: a VIEWER gets 403, ORG_ADMIN still lists it, and the
    caller's own /auth/me exposes the effective permission list the UI uses for navigation."""
    tokens = _register(client, "Directory Gate Org", "admin@dir-gate.com")
    _create_user(client, tokens["access_token"], "viewer@dir-gate.com", role="VIEWER")
    viewer = client.post("/api/v1/auth/login", json={"email": "viewer@dir-gate.com", "password": "staffpassword123"}).json()

    assert client.get("/api/v1/tenant/users", headers=_auth(viewer["access_token"])).status_code == 403
    assert client.get("/api/v1/tenant/teams", headers=_auth(viewer["access_token"])).status_code == 403
    assert client.get("/api/v1/tenant/users", headers=_auth(tokens["access_token"])).status_code == 200

    me_viewer = client.get("/api/v1/auth/me", headers=_auth(viewer["access_token"])).json()
    me_admin = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()
    assert "aircraft:read" in me_viewer["permissions"] and "user:manage" not in me_viewer["permissions"]
    assert "user:manage" in me_admin["permissions"] and "platform:manage" not in me_admin["permissions"]
