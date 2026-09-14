"""HTTP-level tests for GET /lisa/proactive-alerts and GET /lisa/daily-brief:
RBAC, tenant isolation, and the zero-data (brand new org) case."""

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


def test_org_admin_gets_empty_alerts_and_brief_for_new_org(client):
    """A brand-new org with zero aircraft/work orders must get a 200 with
    empty results, not an error -- an honestly-empty result, not a failure."""
    tokens = _register(client, "Proactive Empty Org", "admin@proactive-empty.com")

    alerts_resp = client.get("/api/v1/lisa/proactive-alerts", headers=_auth(tokens["access_token"]))
    assert alerts_resp.status_code == 200
    assert alerts_resp.json() == []

    brief_resp = client.get("/api/v1/lisa/daily-brief", headers=_auth(tokens["access_token"]))
    assert brief_resp.status_code == 200
    brief = brief_resp.json()
    assert brief["critical_count"] == 0
    assert brief["total_count"] == 0
    assert brief["top_priorities"] == []


def test_platform_admin_gets_403_from_proactive_alerts(client, db_session):
    """PLATFORM_ADMIN does not hold AIRCRAFT_READ and must not gain implicit
    visibility into a customer organization's operational alerts."""
    org = Organization(name="Platform Ops For Proactive Test")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email="platform-proactive-test@kotas-aerospace.com",
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
        json={"email": "platform-proactive-test@kotas-aerospace.com", "password": "supersecret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    assert client.get("/api/v1/lisa/proactive-alerts", headers=_auth(token)).status_code == 403
    assert client.get("/api/v1/lisa/daily-brief", headers=_auth(token)).status_code == 403


def test_proactive_alerts_scoped_to_own_organization(client):
    """An ORG_ADMIN in org A must never see org B's AOG-driven alerts, even
    when both have real data."""
    tokens_a = _register(client, "Proactive Tenant A", "admin@proactive-tenant-a.com")
    tokens_b = _register(client, "Proactive Tenant B", "admin@proactive-tenant-b.com")

    aircraft_resp = client.post(
        "/api/v1/aircraft",
        headers=_auth(tokens_a["access_token"]),
        json={"registration": "N999PA", "msn": "MSN-PROACTIVE-1", "aircraft_type": "A320"},
    )
    assert aircraft_resp.status_code == 201
    aircraft_id = aircraft_resp.json()["id"]

    aog_resp = client.post(
        "/api/v1/aog-events",
        headers=_auth(tokens_a["access_token"]),
        json={"aircraft_id": aircraft_id, "root_cause": "Tenant isolation test"},
    )
    assert aog_resp.status_code == 201

    alerts_a = client.get(
        "/api/v1/lisa/proactive-alerts", headers=_auth(tokens_a["access_token"])
    ).json()
    assert any(a["category"] == "AOG" for a in alerts_a)

    alerts_b = client.get(
        "/api/v1/lisa/proactive-alerts", headers=_auth(tokens_b["access_token"])
    ).json()
    assert alerts_b == []
