"""Integration tests for the Developer 1 factual operational state
(asset_service.compute_operational_state, surfaced via
GET /assets/{asset_id}/context's operational_status field).

Covers: AVAILABLE default, GROUNDED (lifecycle status), MAINTENANCE (open
work order), IN_MISSION (active mission), tenant isolation via 404.
"""

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
    import uuid

    return uuid.UUID(
        client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]
    )


def _entitle_features(db_session, org_id, *feature_keys):
    import uuid
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

    plan = Plan(name=f"OS-Plan-{uuid.uuid4().hex[:8]}", code=f"os-plan-{uuid.uuid4().hex[:12]}", is_active=True)
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


def _drone(client, headers, registration="DRN-OS-1"):
    resp = client.post(
        "/api/v1/drones",
        headers=headers,
        json={"registration": registration, "manufacturer": "DJI", "model": "M300"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _context(client, headers, asset_id):
    resp = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_default_operational_state_is_available(client, db_session):
    tokens = _register(client, "Airline OS1", "admin@airline-os1.com")
    headers = _auth(tokens["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers)

    ctx = _context(client, headers, asset_id)
    assert ctx["operational_status"] == "AVAILABLE"


def test_grounded_lifecycle_status_reflected(client, db_session):
    tokens = _register(client, "Airline OS2", "admin@airline-os2.com")
    headers = _auth(tokens["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers, "DRN-OS-2")

    patch_resp = client.patch(
        f"/api/v1/assets/{asset_id}", headers=headers, json={"status": "GROUNDED"}
    )
    assert patch_resp.status_code == 200, patch_resp.text

    ctx = _context(client, headers, asset_id)
    assert ctx["operational_status"] == "GROUNDED"


def test_open_work_order_drives_maintenance_state(client, db_session):
    tokens = _register(client, "Airline OS3", "admin@airline-os3.com")
    headers = _auth(tokens["access_token"])
    org_id = _get_org_id(client, tokens["access_token"])
    _entitle_features(db_session, org_id, "drone_fleet_management", "work_order_management")
    asset_id = _drone(client, headers, "DRN-OS-3")

    wo_resp = client.post(
        "/api/v1/work-orders",
        headers=headers,
        json={"asset_id": asset_id, "work_order_number": "WO-OS-3", "title": "Motor swap"},
    )
    assert wo_resp.status_code == 201, wo_resp.text

    ctx = _context(client, headers, asset_id)
    assert ctx["operational_status"] == "MAINTENANCE"


def test_active_mission_drives_in_mission_state(client, db_session):
    tokens = _register(client, "Airline OS4", "admin@airline-os4.com")
    headers = _auth(tokens["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers, "DRN-OS-4")

    mission_resp = client.post(
        "/api/v1/missions",
        headers=headers,
        json={"asset_id": asset_id, "purpose": "Patrol"},
    )
    mission_id = mission_resp.json()["id"]
    auth_resp = client.post(f"/api/v1/missions/{mission_id}/authorize", headers=headers)
    assert auth_resp.status_code == 200

    ctx = _context(client, headers, asset_id)
    assert ctx["operational_status"] == "IN_MISSION"


def test_operational_state_cross_tenant_isolation(client, db_session):
    tokens_a = _register(client, "Airline OS5A", "admin@airline-os5a.com")
    tokens_b = _register(client, "Airline OS5B", "admin@airline-os5b.com")
    headers_a = _auth(tokens_a["access_token"])
    headers_b = _auth(tokens_b["access_token"])
    _entitle_features(db_session, _get_org_id(client, tokens_a["access_token"]), "drone_fleet_management")
    asset_id = _drone(client, headers_a, "DRN-OS-5")

    resp = client.get(f"/api/v1/assets/{asset_id}/context", headers=headers_b)
    assert resp.status_code == 404
