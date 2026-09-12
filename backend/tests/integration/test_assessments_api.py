"""API-layer tests for the Assessment domain: tenant scoping via the JWT
(never client input), and RBAC enforcement for the new ASSESSMENT_READ /
ASSESSMENT_WRITE permissions.
"""

import uuid

from app.core.security import hash_password
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


def test_org_admin_can_create_list_and_run_assessment(client):
    tokens = _register(client, "Airline API", "admin@airline-api.com")
    headers = _auth(tokens["access_token"])

    create_resp = client.post(
        "/api/v1/assessments", json={"name": "Fleet Assessment"}, headers=headers
    )
    assert create_resp.status_code == 201
    assessment = create_resp.json()
    assert assessment["scope_type"] == "FLEET"
    assert assessment["status"] == "DRAFT"

    list_resp = client.get("/api/v1/assessments", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    run_resp = client.post(f"/api/v1/assessments/{assessment['id']}/run", headers=headers)
    assert run_resp.status_code == 200
    snapshot = run_resp.json()
    assert snapshot["version"] == 1
    assert snapshot["finding_count"] == 0
    assert snapshot["overall_score"] == 100.0

    findings_resp = client.get(f"/api/v1/assessments/{assessment['id']}/findings", headers=headers)
    assert findings_resp.status_code == 200
    assert findings_resp.json() == []


def test_second_tenant_cannot_see_first_tenants_assessment(client):
    tokens_a = _register(client, "Airline A2", "admin@airline-a2.com")
    tokens_b = _register(client, "Airline B2", "admin@airline-b2.com")

    create_resp = client.post(
        "/api/v1/assessments",
        json={"name": "Org A Assessment"},
        headers=_auth(tokens_a["access_token"]),
    )
    assessment_id = create_resp.json()["id"]

    get_resp = client.get(
        f"/api/v1/assessments/{assessment_id}", headers=_auth(tokens_b["access_token"])
    )
    assert get_resp.status_code == 404

    list_resp = client.get("/api/v1/assessments", headers=_auth(tokens_b["access_token"]))
    assert list_resp.status_code == 200
    assert list_resp.json() == []


def test_viewer_role_cannot_write_assessment(client, db_session):
    tokens = _register(client, "Airline Viewer", "admin@airline-viewer.com")
    me = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()
    org_id = uuid.UUID(me["organization_id"])

    viewer = User(
        organization_id=org_id,
        email="viewer@airline-viewer.com",
        hashed_password=hash_password("supersecret123"),
        full_name="Viewer User",
    )
    db_session.add(viewer)
    db_session.commit()
    db_session.refresh(viewer)
    db_session.add(UserRole(user_id=viewer.id, role_name="VIEWER", organization_id=org_id))
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@airline-viewer.com", "password": "supersecret123"},
    )
    assert login_resp.status_code == 200
    viewer_headers = _auth(login_resp.json()["access_token"])

    create_resp = client.post(
        "/api/v1/assessments", json={"name": "Should Fail"}, headers=viewer_headers
    )
    assert create_resp.status_code == 403

    list_resp = client.get("/api/v1/assessments", headers=viewer_headers)
    assert list_resp.status_code == 200
