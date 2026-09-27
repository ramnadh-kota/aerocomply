"""API-layer tests for the Mission domain (backend/app/api/v1/missions.py).

Confirms: creation against a caller-owned asset, listing scoped to
asset_id/status, update, the PLANNED->AUTHORIZED authorization gate (and its
terminal-state rejection), tenant isolation (cross-tenant access 404s), and
authentication enforcement. Mirrors the conventions in test_finding_api.py
and test_drone_lifecycle_api.py.
"""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.deps import get_db_session
from app.main import app
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus


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


def _get_org_id(client, token):
    return uuid.UUID(
        client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]
    )


def _entitle_drone_fleet(db_session, org_id):
    """Ensure org_id has drone_fleet_management enabled."""
    from sqlalchemy import select

    sub = db_session.execute(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
        )
    ).scalars().first()
    if sub:
        pf = db_session.execute(
            select(PlanFeature).where(
                PlanFeature.plan_id == sub.plan_id,
                PlanFeature.feature_key == "drone_fleet_management",
            )
        ).scalar_one_or_none()
        if pf is None:
            db_session.add(PlanFeature(plan_id=sub.plan_id, feature_key="drone_fleet_management", enabled=True))
            db_session.commit()
        elif not pf.enabled:
            pf.enabled = True
            db_session.commit()
        return

    plan = Plan(name=f"Mission-Plan-{org_id}", code=f"mission-plan-{org_id}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(PlanFeature(plan_id=plan.id, feature_key="drone_fleet_management", enabled=True))
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


def _drone(client, headers, registration="DRN-MISSION-1"):
    resp = client.post(
        "/api/v1/drones",
        headers=headers,
        json={"registration": registration, "manufacturer": "DJI", "model": "M300"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _mission(client, headers, asset_id, purpose="Survey", operating_area="Sector 4"):
    resp = client.post(
        "/api/v1/missions",
        headers=headers,
        json={"asset_id": asset_id, "purpose": purpose, "operating_area": operating_area},
    )
    assert resp.status_code == 201
    return resp.json()


def test_create_and_get_mission(client, db_session):
    tokens = _register(client, "Airline Mission1", "admin@airline-mission1.com")
    headers = _auth(tokens["access_token"])
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens["access_token"]))
    asset_id = _drone(client, headers)

    body = _mission(client, headers, asset_id)
    assert body["status"] == "PLANNED"
    assert body["asset_id"] == asset_id
    assert body["purpose"] == "Survey"

    get_resp = client.get(f"/api/v1/missions/{body['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == body["id"]


def test_create_mission_requires_asset_in_organization(client, db_session):
    tokens_a = _register(client, "Airline Mission2A", "admin@airline-mission2a.com")
    tokens_b = _register(client, "Airline Mission2B", "admin@airline-mission2b.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens_a["access_token"]))
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens_b["access_token"]))
    asset_id = _drone(client, headers_a)

    resp = client.post(
        "/api/v1/missions",
        headers=headers_b,
        json={"asset_id": asset_id, "purpose": "Survey"},
    )
    assert resp.status_code == 404


def test_list_missions_scoped_to_asset_and_status(client, db_session):
    tokens = _register(client, "Airline Mission3", "admin@airline-mission3.com")
    headers = _auth(tokens["access_token"])
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens["access_token"]))
    asset_a = _drone(client, headers, "DRN-MISSION-3A")
    asset_b = _drone(client, headers, "DRN-MISSION-3B")

    _mission(client, headers, asset_a, purpose="Mission A1")
    _mission(client, headers, asset_a, purpose="Mission A2")
    _mission(client, headers, asset_b, purpose="Mission B1")

    resp = client.get(f"/api/v1/missions?asset_id={asset_a}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {m["purpose"] for m in body["items"]} == {"Mission A1", "Mission A2"}

    resp = client.get("/api/v1/missions?status=PLANNED", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


def test_update_mission(client, db_session):
    tokens = _register(client, "Airline Mission4", "admin@airline-mission4.com")
    headers = _auth(tokens["access_token"])
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens["access_token"]))
    asset_id = _drone(client, headers)
    mission = _mission(client, headers, asset_id)

    resp = client.patch(
        f"/api/v1/missions/{mission['id']}",
        headers=headers,
        json={"operating_area": "Sector 9", "notes": "Updated plan"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["operating_area"] == "Sector 9"
    assert body["notes"] == "Updated plan"


def test_authorize_mission_lifecycle_and_terminal_state_rejection(client, db_session):
    tokens = _register(client, "Airline Mission5", "admin@airline-mission5.com")
    headers = _auth(tokens["access_token"])
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens["access_token"]))
    asset_id = _drone(client, headers)
    mission = _mission(client, headers, asset_id)

    resp = client.post(f"/api/v1/missions/{mission['id']}/authorize", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "AUTHORIZED"
    assert body["authorized_at"] is not None

    cancel_resp = client.patch(
        f"/api/v1/missions/{mission['id']}", headers=headers, json={"status": "CANCELLED"}
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    reauthorize_resp = client.post(f"/api/v1/missions/{mission['id']}/authorize", headers=headers)
    assert reauthorize_resp.status_code == 400


def test_cross_tenant_mission_access_404s(client, db_session):
    tokens_a = _register(client, "Airline Mission6A", "admin@airline-mission6a.com")
    tokens_b = _register(client, "Airline Mission6B", "admin@airline-mission6b.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens_a["access_token"]))
    _entitle_drone_fleet(db_session, _get_org_id(client, tokens_b["access_token"]))
    asset_id = _drone(client, headers_a)
    mission = _mission(client, headers_a, asset_id)

    resp = client.get(f"/api/v1/missions/{mission['id']}", headers=headers_b)
    assert resp.status_code == 404

    resp = client.patch(
        f"/api/v1/missions/{mission['id']}", headers=headers_b, json={"notes": "hijack"}
    )
    assert resp.status_code == 404

    resp = client.post(f"/api/v1/missions/{mission['id']}/authorize", headers=headers_b)
    assert resp.status_code == 404


def test_mission_endpoints_require_authentication(client):
    resp = client.get("/api/v1/missions")
    assert resp.status_code == 401

    resp = client.post("/api/v1/missions", json={"purpose": "x"})
    assert resp.status_code == 401
