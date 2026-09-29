"""Customer journeys (SIMULATED input) beyond the single-suite drone flow:

  * aircraft customer          - Aircraft suite: aircraft domain works, drone/telemetry domain is closed
  * multi-suite customer       - Drone Professional + Aircraft Enterprise, independent entitlements
  * expired / cancelled        - protected capabilities close, login still works, DATA IS KEPT, and
                                 access returns when a subscription returns
  * data-source failure        - garbage never corrupts stored data or downstream state
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.security import hash_password
from app.models.battery import Battery
from app.models.flight import Flight
from app.models.hums import HUMSSensor, HUMSSensorReading
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.schemas.auth import CurrentUser
from app.services.ai import tools
from app.services.subscription_service import cancel_subscription, create_subscription
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _source
from tests.unit.test_m20_mavlink_integrity import heartbeat, vibration

PW = "TestPassword123!"
DRONE_FEATURES = ["drone_fleet_management", "flight_telemetry", "hums", "battery_analytics",
                  "work_order_management", "lisa_ai_copilot"]
AIRCRAFT_FEATURES = ["aircraft_fleet_management", "work_order_management", "compliance_management"]


def _plan(db, suite_code, features):
    suite = db.execute(select(ProductSuite).where(ProductSuite.code == suite_code)).scalar_one()
    plan = Plan(suite_id=suite.id, code=f"J-{uuid.uuid4().hex[:8]}", name=f"{suite_code} Pro", is_active=True)
    db.add(plan)
    db.flush()
    for f in features:
        db.add(PlanFeature(plan_id=plan.id, feature_key=f, enabled=True))
    db.flush()
    return plan


def _customer(client, db, plans):
    """Organization with one ACTIVE subscription per plan (one per suite) and an ORG_ADMIN login."""
    org = Organization(name=f"Cust {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    subs = [
        create_subscription(db, actor_user_id=None, organization_id=org.id, plan_id=p.id,
                            status=SubscriptionStatus.ACTIVE, starts_at=datetime.now(UTC) - timedelta(days=1))
        for p in plans
    ]
    u = User(organization_id=org.id, email=f"c-{uuid.uuid4().hex[:8]}@example.com",
             hashed_password=hash_password(PW), full_name="Cust Admin", is_active=True, email_verified=True)
    db.add(u)
    db.flush()
    db.add(UserRole(user_id=u.id, role_name="ORG_ADMIN", organization_id=org.id))
    db.commit()
    tok = client.post("/api/v1/auth/login", json={"email": u.email, "password": PW}).json()["access_token"]
    return org, subs, {"Authorization": f"Bearer {tok}"}, u


def _code(resp):
    return resp.json().get("error", {}).get("code")


# ------------------------------------------------------------------ aircraft customer
def test_aircraft_customer_gets_aircraft_domain_and_not_drone_or_telemetry(client, db_session):
    org, subs, h, _ = _customer(client, db_session, [_plan(db_session, "AIRCRAFT", AIRCRAFT_FEATURES)])
    created = client.post("/api/v1/aircraft", headers=h, json={
        "registration": "VT-JRN", "msn": "MSN-1", "aircraft_type": "A320", "manufacturer": "Airbus"})
    assert created.status_code == 201, created.text
    assert client.get("/api/v1/aircraft", headers=h).status_code == 200
    assert client.get("/api/v1/work-orders", headers=h).status_code == 200

    ent = client.get("/api/v1/entitlements", headers=h).json()
    assert ent["suite_code"] == "AIRCRAFT" and ent["effective_features"].get("aircraft_fleet_management") is True
    assert "drone_fleet_management" not in ent["effective_features"]

    for path in ("/api/v1/drones", "/api/v1/batteries/" + str(uuid.uuid4()),
                 "/api/v1/telemetry/events", "/api/v1/hums/sensors"):
        r = client.get(path, headers=h)
        assert r.status_code == 403, (path, r.status_code)
    assert _code(client.get("/api/v1/drones", headers=h)) == "SUITE_ENTITLEMENT_REQUIRED"

    # LISA is bound by the same entitlements: an aircraft tool answers, HUMS/telemetry tools refuse
    user = CurrentUser(id=uuid.uuid4(), organization_id=org.id, roles=["ORG_ADMIN"], email="x@example.com",
                       full_name="X", email_verified=True)
    assert tools.execute_tool(db_session, user, "list_aircraft", {})
    from app.core.errors import ForbiddenError
    import pytest

    with pytest.raises(ForbiddenError):
        tools.execute_tool(db_session, user, "get_asset_hums_health", {"asset_id": str(uuid.uuid4())})


# ------------------------------------------------------------------ multi-suite customer
def test_multi_suite_customer_has_independent_entitlements(client, db_session):
    drone_plan = _plan(db_session, "DRONE_UAV", DRONE_FEATURES)
    aircraft_plan = _plan(db_session, "AIRCRAFT", AIRCRAFT_FEATURES)
    org, subs, h, _ = _customer(client, db_session, [drone_plan, aircraft_plan])
    drone_sub, aircraft_sub = subs

    ent = client.get("/api/v1/entitlements", headers=h).json()
    assert {s["suite_code"] for s in ent["active_suites"]} == {"DRONE_UAV", "AIRCRAFT"}
    assert client.get("/api/v1/drones", headers=h).status_code == 200
    assert client.get("/api/v1/aircraft", headers=h).status_code == 200
    assert client.get("/api/v1/telemetry/events", headers=h).status_code == 200

    # cancel ONLY the drone subscription: aircraft keeps working, drone/telemetry close
    cancel_subscription(db_session, actor_user_id=None, subscription_id=drone_sub.id)
    assert client.get("/api/v1/aircraft", headers=h).status_code == 200
    assert client.get("/api/v1/work-orders", headers=h).status_code == 200
    for path in ("/api/v1/drones", "/api/v1/telemetry/events"):
        assert client.get(path, headers=h).status_code == 403, path
    after = client.get("/api/v1/entitlements", headers=h).json()
    assert {s["suite_code"] for s in after["active_suites"]} == {"AIRCRAFT"}


# ------------------------------------------------------------------ expired / cancelled customer
def test_expired_customer_is_closed_but_data_is_retained_and_access_returns(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", DRONE_FEATURES)
    org, subs, h, _ = _customer(client, db_session, [plan])
    asset = _drone(client, h, reg="EXP-1")
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    assert _ingest(client, h, sid, heartbeat(seq=1) + vibration(2, 2, 2, seq=2)).json()["accepted"] == 2

    def readings():
        return db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org.id))

    assert readings() == 1

    # subscription lapses
    sub = db_session.get(Subscription, subs[0].id)
    sub.ends_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    assert client.get("/api/v1/auth/me", headers=h).status_code == 200        # identity still valid
    ent = client.get("/api/v1/entitlements", headers=h).json()
    assert ent["resolution_status"] == "NO_SUBSCRIPTION" and ent["effective_features"] == {}
    for method, path in (("GET", "/api/v1/drones"), ("GET", f"/api/v1/telemetry/assets/{asset}/latest"),
                         ("GET", f"/api/v1/data-sources/{sid}/health"), ("POST", f"/api/v1/data-sources/{sid}/ingest")):
        r = client.request(method, path, headers=h, content=b"x" if method == "POST" else None)
        assert r.status_code == 403, (path, r.status_code)
    assert readings() == 1                                                     # nothing deleted, nothing added

    # a new subscription restores access to the SAME data
    create_subscription(db_session, actor_user_id=None, organization_id=org.id, plan_id=plan.id,
                        status=SubscriptionStatus.ACTIVE, starts_at=datetime.now(UTC))  # renewal starts when the old term ended
    latest = client.get(f"/api/v1/telemetry/assets/{asset}/latest", headers=h)
    assert latest.status_code == 200 and latest.json()["sensor_count"] == 1


# ------------------------------------------------------------------ data-source failure
def test_source_failure_never_corrupts_stored_data_or_downstream_state(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", DRONE_FEATURES)
    org, subs, h, _ = _customer(client, db_session, [plan])
    asset = _drone(client, h, reg="FAIL-1")
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    assert _ingest(client, h, sid, heartbeat(seq=1) + vibration(2, 2, 2, seq=2)).json()["accepted"] == 2

    def snapshot():
        return (
            db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org.id)),
            db_session.scalar(select(func.count(Flight.id)).where(Flight.organization_id == org.id)),
            db_session.scalar(select(func.count(HUMSSensor.id)).where(HUMSSensor.organization_id == org.id)),
            tuple(db_session.scalars(select(Battery.cycle_count).where(Battery.organization_id == org.id))),
        )

    before = snapshot()
    bad = bytearray(vibration(9, 9, 9, seq=3)); bad[15] ^= 0xFF
    garbage = [
        b"\x00\x01\x02not mavlink at all" * 40,
        bytes(bad),                                                # checksum failure
        vibration(9, 9, 9, seq=2),                                 # duplicate sequence
        vibration(9, 9, 9, seq=4, sysid=99),                       # unmapped vehicle
        heartbeat(seq=5, sysid=255, compid=190),                   # ground station
    ]
    for chunk in garbage:
        r = _ingest(client, h, sid, chunk)
        assert r.status_code == 200 and r.json()["accepted"] == 0, (chunk[:8], r.text)
    assert snapshot() == before                                    # not one row changed

    health = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert health["event_count"] == 2                              # only the two real frames
    assert health["error_count"] >= 1 and health["last_failure_at"] and health["consecutive_failures"] >= 1

    # the source recovers by itself when good data returns
    ok = _ingest(client, h, sid, vibration(3, 3, 3, seq=6)).json()
    assert ok["accepted"] == 1
    recovered = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert recovered["consecutive_failures"] == 0 and recovered["status"] == "HEALTHY"
    assert snapshot()[0] == before[0] + 1


def test_hostile_payloads_never_crash_the_ingest_endpoint(client, db_session):
    plan = _plan(db_session, "DRONE_UAV", DRONE_FEATURES)
    org, subs, h, _ = _customer(client, db_session, [plan])
    asset = _drone(client, h, reg="HOSTILE-1")
    csv_sid = _source(client, h, "CSV_BATCH")
    json_sid = _source(client, h, "JSON_BATCH")
    mqtt_sid = _source(client, h, "MQTT")
    deep = ("[" * 5000 + "]" * 5000).encode()                        # recursion bomb
    cases = [
        (csv_sid, b"\xff\xfe\x00\x00binary\x00junk"),
        (csv_sid, b"asset_id,value\n" + b"HOSTILE-1,1e999\n" * 50),      # overflow to inf
        (csv_sid, ('asset_id,value,timestamp\nHOSTILE-1,1,"=cmd|\' /C calc\'!A0"\n').encode()),
        (json_sid, deep),
        (json_sid, b'{"a":' * 3000),
        (json_sid, json.dumps([{"asset_id": "HOSTILE-1", "value": "NaN", "temperature": float(1e308) * 10}]).encode()
         if False else b'[{"asset_id":"HOSTILE-1","temperature":Infinity}]'),
        (mqtt_sid, b"\x89PNG\r\n"),
        (mqtt_sid, json.dumps({"asset_id": "HOSTILE-1", "sensor_code": "T", "value": "x" * 10000}).encode()),
        (mqtt_sid, json.dumps({"asset_id": "HOSTILE-1", "sensor_code": "T", "value": 1, "timestamp": 10 ** 30}).encode()),
    ]
    for sid, body in cases:
        r = _ingest(client, h, sid, body)
        assert r.status_code < 500, (sid, body[:30], r.status_code, r.text[:200])
        if r.status_code == 200:
            assert r.json()["accepted"] == 0, (body[:30], r.json())
    assert db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org.id)) == 0
