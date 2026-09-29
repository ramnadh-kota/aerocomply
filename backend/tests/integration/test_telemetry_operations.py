"""Phase C: telemetry as a customer capability -- register asset, connect source, receive data,
see latest state, quality, history, flights. Real HTTP + real database; simulated input only."""
from __future__ import annotations

import csv
import io
import uuid

from tests.integration.test_acquisition_pipeline import (
    _csv, _drone, _ingest, _org, _source,
)
from tests.unit.test_m20_mavlink_integrity import heartbeat, sys_status, vibration


def _seed_stream(client, h):
    asset = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    stream = (heartbeat(seq=1) + sys_status(seq=2, remaining=88) + vibration(2, 2, 2, seq=3)
              + vibration(4, 4, 4, seq=4))
    rep = _ingest(client, h, sid, stream).json()
    assert rep["accepted"] == 4, rep
    return asset, sid


def test_latest_status_history_and_flights_reflect_ingested_data(client, db_session):
    org_id, h = _org(client, db_session)
    asset, _ = _seed_stream(client, h)

    latest = client.get(f"/api/v1/telemetry/assets/{asset}/latest", headers=h).json()
    codes = {s["sensor_code"]: s for s in latest["sensors"]}
    assert "VIB_MAIN_SYS1" in codes
    assert codes["VIB_MAIN_SYS1"]["value"] == 4.0          # the newest of (2.0, 4.0)
    assert codes["VIB_MAIN_SYS1"]["age_seconds"] < 60
    assert codes["VIB_MAIN_SYS1"]["data_quality"] == "VALID"
    assert latest["sensor_count"] == len(latest["sensors"]) >= 1

    hist = client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h,
                      params={"sensor_code": "VIB_MAIN_SYS1"}).json()
    assert hist["total"] == 2 and [i["value"] for i in hist["items"]] == [4.0, 2.0]   # newest first

    page = client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h,
                      params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["items"][0]["value"] == 2.0

    status = client.get(f"/api/v1/telemetry/assets/{asset}/status", headers=h).json()
    assert status["telemetry_state"] == "ACTIVE" and status["last_received_at"]

    flights = client.get(f"/api/v1/telemetry/assets/{asset}/flights", headers=h).json()
    assert len(flights) == 1 and flights[0]["cycles"] == 1


def test_asset_without_telemetry_reports_it_honestly(client, db_session):
    org_id, h = _org(client, db_session)
    asset = _drone(client, h)
    assert client.get(f"/api/v1/telemetry/assets/{asset}/latest", headers=h).json()["sensors"] == []
    assert client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h).json()["items"] == []
    st = client.get(f"/api/v1/telemetry/assets/{asset}/status", headers=h).json()
    assert st["telemetry_state"] == "NO_TELEMETRY_RECORDED" and st["last_received_at"] is None
    assert client.get(f"/api/v1/telemetry/assets/{asset}/flights", headers=h).json() == []


def test_history_window_defaults_to_24h_and_can_be_widened(client, db_session):
    org_id, h = _org(client, db_session)
    asset = _drone(client, h, reg="HW-1")
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "HW-1", "sensor_code": "T", "value": "9", "unit": "C",
                  "timestamp": "2026-01-01T00:00:00Z"}])
    assert _ingest(client, h, sid, body).json()["accepted"] == 1
    assert client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h).json()["items"] == []
    wide = client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h,
                      params={"since": "2025-12-31T00:00:00Z"}).json()
    assert [i["value"] for i in wide["items"]] == [9.0]


def test_history_limit_is_capped(client, db_session):
    org_id, h = _org(client, db_session)
    asset = _drone(client, h)
    r = client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h, params={"limit": 5000})
    assert r.status_code == 422


def test_other_tenants_asset_is_indistinguishable_from_a_missing_one(client, db_session):
    org_a, ha = _org(client, db_session, "a")
    org_b, hb = _org(client, db_session, "b")
    asset, _ = _seed_stream(client, ha)
    for suffix in ("latest", "history", "status", "flights"):
        real = client.get(f"/api/v1/telemetry/assets/{asset}/{suffix}", headers=hb)
        rand = client.get(f"/api/v1/telemetry/assets/{uuid.uuid4()}/{suffix}", headers=hb)
        assert real.status_code == rand.status_code == 404, (suffix, real.status_code)
        assert asset not in real.text


def test_event_listing_has_real_total_and_filters(client, db_session):
    org_id, h = _org(client, db_session)
    asset, _ = _seed_stream(client, h)
    r = client.get("/api/v1/telemetry/events", headers=h, params={"limit": 2}).json()
    assert r["total"] == 4 and len(r["items"]) == 2               # was len(page) before
    only = client.get("/api/v1/telemetry/events", headers=h,
                      params={"asset_id": asset, "processing_status": "processed"}).json()
    assert only["total"] == 4
    none = client.get("/api/v1/telemetry/events", headers=h, params={"processing_status": "QUARANTINED"}).json()
    assert none["total"] == 0


def test_read_endpoints_require_the_telemetry_feature(client, db_session):
    from app.core.security import hash_password
    from app.models.organization import Organization
    from app.models.user import User, UserRole
    from tests.integration.conftest import grant_features

    org = Organization(name=f"nf-{uuid.uuid4().hex[:6]}")
    db_session.add(org); db_session.flush()
    grant_features(db_session, org.id, "drone_fleet_management")
    u = User(organization_id=org.id, email=f"nf-{uuid.uuid4().hex[:6]}@example.com",
             hashed_password=hash_password("TestPassword123!"), full_name="N", is_active=True, email_verified=True)
    db_session.add(u); db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_name="ORG_ADMIN", organization_id=org.id))
    db_session.commit()
    tok = client.post("/api/v1/auth/login", json={"email": u.email, "password": "TestPassword123!"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    for suffix in ("latest", "history", "status", "flights"):
        assert client.get(f"/api/v1/telemetry/assets/{uuid.uuid4()}/{suffix}", headers=h).status_code == 403
