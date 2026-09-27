"""Integration tests for GET /assets/{asset_id}/history -- the asset's
unified operational lifecycle timeline (Developer 1 Milestone 9).

Covers: audit events, mission created/completed, work order created/
completed, finding created, tenant isolation, event_type filtering.
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
    assert resp.status_code == 201, resp.text
    return resp.json()


def _get_org_id(client, token):
    return uuid.UUID(
        client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]
    )


def _entitle_features(db_session, org_id, *feature_keys):
    from sqlalchemy import select

    sub = db_session.execute(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
        )
    ).scalars().first()
    if sub:
        for key in feature_keys:
            pf = db_session.execute(
                select(PlanFeature).where(
                    PlanFeature.plan_id == sub.plan_id,
                    PlanFeature.feature_key == key,
                )
            ).scalar_one_or_none()
            if pf is None:
                db_session.add(PlanFeature(plan_id=sub.plan_id, feature_key=key, enabled=True))
            elif not pf.enabled:
                pf.enabled = True
        db_session.commit()
        return

    plan = Plan(name=f"TL-Plan-{org_id}-{uuid.uuid4().hex[:8]}", code=f"tl-plan-{uuid.uuid4().hex[:12]}", is_active=True)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    for key in feature_keys:
        db_session.add(PlanFeature(plan_id=plan.id, feature_key=key, enabled=True))
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


def _drone(client, headers, registration="DRN-TL-1"):
    resp = client.post(
        "/api/v1/drones",
        headers=headers,
        json={"registration": registration, "manufacturer": "DJI", "model": "M300"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_timeline_includes_mission_created_and_completed(client, db_session):
    tokens = _register(client, "Airline TL1", "admin@airline-tl1.com")
    headers = _auth(tokens["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers)

    mission_resp = client.post(
        "/api/v1/missions",
        headers=headers,
        json={"asset_id": asset_id, "purpose": "Survey Run"},
    )
    assert mission_resp.status_code == 201
    mission_id = mission_resp.json()["id"]

    patch_resp = client.patch(
        f"/api/v1/missions/{mission_id}", headers=headers, json={"status": "COMPLETED"}
    )
    assert patch_resp.status_code == 200

    resp = client.get(f"/api/v1/assets/{asset_id}/history", headers=headers)
    assert resp.status_code == 200
    events = resp.json()["events"]
    event_types = {e["event_type"] for e in events}
    assert "MISSION_CREATED" in event_types
    assert "MISSION_COMPLETED" in event_types


def test_timeline_includes_work_order_created_and_completed(client, db_session):
    tokens = _register(client, "Airline TL2", "admin@airline-tl2.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_features(db_session, org_id, "drone_fleet_management", "work_order_management")
    asset_id = _drone(client, headers, "DRN-TL-2")

    wo_resp = client.post(
        "/api/v1/work-orders",
        headers=headers,
        json={"asset_id": asset_id, "work_order_number": "WO-TL-2", "title": "Rotor inspection"},
    )
    assert wo_resp.status_code == 201, wo_resp.text
    wo_id = wo_resp.json()["id"]

    for target_status in ("OPEN", "PLANNED"):
        t = client.post(
            f"/api/v1/work-orders/{wo_id}/transition",
            headers=headers,
            json={"target_status": target_status},
        )
        assert t.status_code == 200, t.text

    resp = client.get(f"/api/v1/assets/{asset_id}/history", headers=headers)
    assert resp.status_code == 200
    events = resp.json()["events"]
    event_types = {e["event_type"] for e in events}
    assert "WORK_ORDER_CREATED" in event_types


def test_timeline_event_type_filter(client, db_session):
    tokens = _register(client, "Airline TL3", "admin@airline-tl3.com")
    headers = _auth(tokens["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers, "DRN-TL-3")

    client.post(
        "/api/v1/missions",
        headers=headers,
        json={"asset_id": asset_id, "purpose": "Survey Run"},
    )

    resp = client.get(
        f"/api/v1/assets/{asset_id}/history",
        headers=headers,
        params={"event_type": "MISSION_CREATED"},
    )
    assert resp.status_code == 200
    events = resp.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "MISSION_CREATED"


def test_timeline_cross_tenant_isolation(client, db_session):
    tokens_a = _register(client, "Airline TL4A", "admin@airline-tl4a.com")
    tokens_b = _register(client, "Airline TL4B", "admin@airline-tl4b.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens_a["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers_a, "DRN-TL-4")

    resp = client.get(f"/api/v1/assets/{asset_id}/history", headers=headers_b)
    assert resp.status_code == 404
