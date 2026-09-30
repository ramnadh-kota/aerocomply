"""B5/B6/B8/B9/B14: the acquisition pipeline, end to end over real HTTP + real database.

    DataSource -> connector -> NormalizedTelemetryEvent -> telemetry persistence
               -> asset / flight / sensor / reading rows -> DataSource health evidence

Everything below is SIMULATED input (bytes built in-process): no broker, no radio, no
vehicle. It proves the software path, not RF/hardware behaviour.
"""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models.asset import Asset
from app.models.data_source import DataSource
from app.models.flight import Flight
from app.models.hums import HUMSSensorReading
from app.models.telemetry import ExternalAssetMapping, TelemetryEventLog
from app.services import acquisition_service
from tests.unit.test_m20_mavlink_integrity import heartbeat, sys_status, vibration

PW = "TestPassword123!"


# ------------------------------------------------------------------ helpers
def _org(client, db_session, tag="acq"):
    from tests.integration.conftest import make_platform_admin_headers

    pa = make_platform_admin_headers(client, db_session)
    r = client.post(
        "/api/v1/auth/register-organization",
        json={"organization_name": f"{tag}-{uuid.uuid4().hex[:8]}",
              "admin_email": f"{tag}-{uuid.uuid4().hex[:8]}@example.com",
              "admin_password": PW, "admin_full_name": "Admin"},
        headers=pa,
    )
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    org_id = client.get("/api/v1/auth/me", headers=h).json()["organization_id"]
    return uuid.UUID(org_id), h


def _drone(client, h, reg=None):
    r = client.post("/api/v1/drones", headers=h, json={
        "registration": reg or f"D-{uuid.uuid4().hex[:6]}", "manufacturer": "DJI", "model": "M300"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _source(client, h, ctype, config=None, *, active=True, **extra):
    r = client.post("/api/v1/data-sources", headers=h, json={
        "name": f"src-{uuid.uuid4().hex[:8]}", "connector_type": ctype,
        "connection_config": config or {}, **extra})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    if active:
        assert client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": "ACTIVE"}).status_code == 200
    return sid


def _ingest(client, h, sid, body: bytes, **params):
    return client.post(f"/api/v1/data-sources/{sid}/ingest", headers=h, content=body,
                       params=params, )


def _readings(db, org_id, asset_id):
    return db.scalar(select(func.count(HUMSSensorReading.id)).where(
        HUMSSensorReading.organization_id == org_id, HUMSSensorReading.asset_id == uuid.UUID(asset_id)))


def _flights(db, org_id, asset_id):
    return db.scalar(select(func.count(Flight.id)).where(
        Flight.organization_id == org_id, Flight.asset_id == uuid.UUID(asset_id)))


def _csv(rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode()


# ------------------------------------------------------------------ MAVLink: multi-vehicle
def test_mavlink_multi_vehicle_routes_each_stream_to_its_own_asset(client, db_session):
    org_id, h = _org(client, db_session)
    a1, a2 = _drone(client, h), _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": a1, "2": a2}})

    stream = (heartbeat(seq=1, sysid=1) + vibration(3, 3, 3, seq=2, sysid=1)
              + heartbeat(seq=1, sysid=2) + vibration(9, 9, 9, seq=2, sysid=2))  # same seq, other vehicle
    r = _ingest(client, h, sid, stream)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["accepted"] == 4 and rep["duplicates"] == 0 and rep["quarantined"] == 0

    vals = {}
    for asset in (a1, a2):
        rows = db_session.execute(select(HUMSSensorReading.value).where(
            HUMSSensorReading.organization_id == org_id, HUMSSensorReading.asset_id == uuid.UUID(asset))).scalars().all()
        vals[asset] = rows
    assert vals[a1] == [3.0] and vals[a2] == [9.0]          # never crossed
    assert _flights(db_session, org_id, a1) == 1 and _flights(db_session, org_id, a2) == 1


def test_mavlink_duplicate_loss_and_corruption_are_reported_and_counted(client, db_session):
    org_id, h = _org(client, db_session)
    a1 = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": a1}})
    good = vibration(1, 1, 1, seq=10)
    bad = bytearray(vibration(1, 1, 1, seq=11)); bad[12] ^= 0xFF
    stream = good + good + bytes(bad) + vibration(1, 1, 1, seq=15)   # dup, corrupt, loss of 11..14
    rep = _ingest(client, h, sid, stream).json()
    assert rep["accepted"] == 2
    assert rep["duplicates"] == 1
    assert rep["rejected"] >= 1
    assert rep["packets_lost"] == 4
    assert _readings(db_session, org_id, a1) == 2

    health = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert health["event_count"] == 2 and health["duplicate_count"] == 1 and health["loss_count"] == 4
    assert health["last_success_at"] and health["latency_ms"] is not None


def test_mavlink_unknown_vehicle_is_quarantined_not_attached(client, db_session):
    org_id, h = _org(client, db_session)
    a1 = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": a1}})
    rep = _ingest(client, h, sid, vibration(5, 5, 5, seq=1, sysid=7)).json()   # sysid 7 unmapped
    assert rep["accepted"] == 0 and rep["quarantined"] == 1
    assert _readings(db_session, org_id, a1) == 0
    log = db_session.execute(select(TelemetryEventLog).where(
        TelemetryEventLog.organization_id == org_id, TelemetryEventLog.processing_status == "QUARANTINED")).scalars().all()
    assert len(log) == 1 and log[0].asset_id is None


def test_streaming_frames_produce_one_flight_per_vehicle(client, db_session):
    org_id, h = _org(client, db_session)
    a1 = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": a1}})
    for i in range(1, 6):
        _ingest(client, h, sid, vibration(1, 1, 1, seq=i))
    assert _flights(db_session, org_id, a1) == 1


# ------------------------------------------------------------------ B6 asset resolution
def test_ambiguous_identifier_quarantines_instead_of_guessing(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="TWIN-1")                       # registration TWIN-1
    b = _drone(client, h)
    db_session.execute(Asset.__table__.update().where(Asset.id == uuid.UUID(b)).values(serial_number="TWIN-1"))
    db_session.commit()                                        # another asset has SERIAL TWIN-1
    sid = _source(client, h, "JSON_BATCH")
    body = json.dumps([{"asset_id": "TWIN-1", "temperature": 40.0}]).encode()
    rep = _ingest(client, h, sid, body).json()
    assert rep["accepted"] == 0 and rep["quarantined"] == 1
    assert "ambiguous" in " ".join(rep["warnings"]).lower()
    assert _readings(db_session, org_id, a) == 0 and _readings(db_session, org_id, b) == 0


def test_quarantined_event_can_be_replayed_after_mapping_is_fixed(client, db_session):
    """Previously this crashed on the (org, source, event_id) unique constraint."""
    org_id, h = _org(client, db_session)
    a = _drone(client, h)
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "EXT-LATE", "sensor_code": "TEMP", "value": "31.5", "unit": "C",
                  "timestamp": "2026-01-01T00:00:00Z"}])
    first = _ingest(client, h, sid, body).json()
    assert first["quarantined"] == 1 and first["accepted"] == 0
    r = client.post("/api/v1/telemetry/asset-mappings", headers=h, json={
        "source_system": "CSV_BATCH", "external_asset_id": "EXT-LATE", "asset_id": a})
    assert r.status_code in (200, 201), r.text
    again = _ingest(client, h, sid, body)
    assert again.status_code == 200, again.text
    assert again.json()["accepted"] == 1 and again.json()["quarantined"] == 0
    rows = db_session.execute(select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org_id)).scalars().all()
    assert len(rows) == 1 and rows[0].processing_status == "PROCESSED" and rows[0].rejection_reason is None


def test_soft_deleted_asset_never_receives_telemetry(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="DEL-1")
    db_session.execute(Asset.__table__.update().where(Asset.id == uuid.UUID(a)).values(deleted_at=datetime.now(UTC)))
    db_session.commit()
    sid = _source(client, h, "JSON_BATCH")
    rep = _ingest(client, h, sid, json.dumps([{"asset_id": "DEL-1", "temperature": 1.0}]).encode()).json()
    assert rep["accepted"] == 0 and rep["quarantined"] == 1


# ------------------------------------------------------------------ B8 quality
def test_future_and_ancient_timestamps_are_rejected_not_stored(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="Q-1")
    sid = _source(client, h, "CSV_BATCH")
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    body = _csv([
        {"asset_id": "Q-1", "sensor_code": "T", "value": "1", "unit": "C", "timestamp": future},
        {"asset_id": "Q-1", "sensor_code": "T", "value": "2", "unit": "C", "timestamp": "1970-01-02T00:00:00Z"},
        {"asset_id": "Q-1", "sensor_code": "T", "value": "3", "unit": "C", "timestamp": "2026-01-01T00:00:00Z"},
    ])
    rep = _ingest(client, h, sid, body).json()
    assert rep["accepted"] == 1 and rep["rejected"] == 2
    assert _readings(db_session, org_id, a) == 1
    statuses = sorted(x for x in db_session.execute(select(TelemetryEventLog.processing_status).where(
        TelemetryEventLog.organization_id == org_id)).scalars())
    assert statuses == ["PROCESSED", "REJECTED", "REJECTED"]


def test_unparseable_timestamp_is_an_error_not_silently_now(client, db_session):
    org_id, h = _org(client, db_session)
    _drone(client, h, reg="Q-2")
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "Q-2", "sensor_code": "T", "value": "1", "unit": "C", "timestamp": "not-a-date"}])
    rep = _ingest(client, h, sid, body).json()
    assert rep["accepted"] == 0 and rep["rejected"] == 1
    assert any("timestamp" in e.lower() for e in rep["errors"])


def test_nan_and_infinity_values_are_rejected(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="Q-3")
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "Q-3", "sensor_code": "T", "value": v, "unit": "C", "timestamp": "2026-01-01T00:00:0%dZ" % i}
                 for i, v in enumerate(["nan", "inf", "-inf", "5"])])
    rep = _ingest(client, h, sid, body).json()
    assert rep["accepted"] == 1 and rep["rejected"] == 3
    assert _readings(db_session, org_id, a) == 1


# ------------------------------------------------------------------ batch idempotency / collisions
def test_reuploading_a_file_is_idempotent(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="B-1")
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "B-1", "sensor_code": "T", "value": str(i), "unit": "C",
                  "timestamp": f"2026-01-01T00:00:0{i}Z"} for i in range(5)])
    assert _ingest(client, h, sid, body).json()["accepted"] == 5
    again = _ingest(client, h, sid, body).json()
    assert again["accepted"] == 0 and again["duplicates"] == 5
    assert _readings(db_session, org_id, a) == 5


def test_two_vehicles_with_the_same_start_time_do_not_collide(client, db_session):
    """Old id was <connector>-R<row>-<ts>: row 2 of two different files at the same timestamp
    became the SAME event and the second vehicle's data was dropped as a 'duplicate'."""
    org_id, h = _org(client, db_session)
    a1, a2 = _drone(client, h, reg="C-1"), _drone(client, h, reg="C-2")
    sid = _source(client, h, "CSV_BATCH")
    row = lambda reg, v: _csv([{"asset_id": reg, "sensor_code": "T", "value": v, "unit": "C", "timestamp": "2026-01-01T00:00:00Z"}])
    assert _ingest(client, h, sid, row("C-1", "10")).json()["accepted"] == 1
    assert _ingest(client, h, sid, row("C-2", "20")).json()["accepted"] == 1
    assert _readings(db_session, org_id, a1) == 1 and _readings(db_session, org_id, a2) == 1


def test_column_priority_is_deterministic(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="PRIM-ID")
    _drone(client, h, reg="SEC-ID")
    sid = _source(client, h, "CSV_BATCH")
    body = _csv([{"asset_id": "PRIM-ID", "device_sn": "SEC-ID", "sensor_code": "T", "value": "1", "unit": "C",
                  "timestamp": "2026-01-01T00:00:00Z"}])
    assert _ingest(client, h, sid, body).json()["accepted"] == 1
    assert _readings(db_session, org_id, a) == 1


# ------------------------------------------------------------------ MQTT
def test_mqtt_uses_device_timestamp_and_dedupes_redelivery(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="M-1")
    sid = _source(client, h, "MQTT", {"topic_filter": "kota/#"})
    ts = "2026-01-01T12:00:00Z"
    msg = json.dumps({"asset_id": "M-1", "sensor_code": "VIB", "value": 2.5, "unit": "mm/s", "timestamp": ts}).encode()
    first = _ingest(client, h, sid, msg, topic="kota/telemetry/M-1").json()
    redelivered = _ingest(client, h, sid, msg, topic="kota/telemetry/M-1").json()
    assert first["accepted"] == 1 and redelivered["duplicates"] == 1 and redelivered["accepted"] == 0
    rec = db_session.execute(select(HUMSSensorReading).where(HUMSSensorReading.organization_id == org_id)).scalar_one()
    assert rec.recorded_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)      # device time, not arrival


def test_mqtt_payload_asset_outranks_topic_segment(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="M-2")
    sid = _source(client, h, "MQTT")
    msg = json.dumps({"asset_id": "M-2", "sensor_code": "T", "value": 1.0, "unit": "C"}).encode()
    assert _ingest(client, h, sid, msg, topic="kota/PING").json()["accepted"] == 1
    assert _readings(db_session, org_id, a) == 1


# ------------------------------------------------------------------ lifecycle, gating, tenancy
@pytest.mark.parametrize("state", ["DRAFT", "PAUSED", "DECOMMISSIONED"])
def test_non_active_source_refuses_data(client, db_session, state):
    org_id, h = _org(client, db_session)
    sid = _source(client, h, "CSV_BATCH", active=False)
    if state != "DRAFT":
        client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": "ACTIVE"})
        client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": state})
    r = _ingest(client, h, sid, b"asset_id,value\nX,1\n")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "data_source_not_active"


@pytest.mark.parametrize("ctype", ["DJI_FLIGHTHUB", "OEM_API"])
def test_unsupported_connector_types_fail_with_structured_error(client, db_session, ctype):
    org_id, h = _org(client, db_session)
    sid = _source(client, h, ctype)
    r = _ingest(client, h, sid, b"{}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "unsupported_connector_type"


def test_other_tenants_source_is_404_and_unwritable(client, db_session):
    org_a, ha = _org(client, db_session, "a")
    org_b, hb = _org(client, db_session, "b")
    a = _drone(client, ha, reg="ISO-A")
    sid = _source(client, ha, "JSON_BATCH")
    body = json.dumps([{"asset_id": "ISO-A", "temperature": 1.0}]).encode()
    assert _ingest(client, hb, sid, body).status_code == 404
    assert client.get(f"/api/v1/data-sources/{sid}/health", headers=hb).status_code == 404
    assert _readings(db_session, org_a, a) == 0


def test_foreign_default_asset_cannot_be_bound(client, db_session):
    org_a, ha = _org(client, db_session, "a")
    org_b, hb = _org(client, db_session, "b")
    foreign = _drone(client, ha)
    r = client.post("/api/v1/data-sources", headers=hb, json={
        "name": "steal", "connector_type": "MQTT", "default_asset_id": foreign})
    assert r.status_code == 404
    mine = _source(client, hb, "MQTT", active=False)
    r = client.patch(f"/api/v1/data-sources/{mine}", headers=hb, json={"default_asset_id": foreign})
    assert r.status_code == 404


def test_single_asset_binding_is_explicit_and_tenant_checked(client, db_session):
    org_id, h = _org(client, db_session)
    a = _drone(client, h)
    sid = _source(client, h, "JSON_BATCH", {"asset_binding": "SINGLE_ASSET"}, default_asset_id=a)
    rep = _ingest(client, h, sid, json.dumps([{"asset_id": "ignored", "temperature": 7.0}]).encode()).json()
    assert rep["accepted"] == 1 and _readings(db_session, org_id, a) == 1
    # default_asset_id WITHOUT the explicit opt-in is never used for attribution
    sid2 = _source(client, h, "JSON_BATCH", {}, default_asset_id=a)
    rep2 = _ingest(client, h, sid2, json.dumps([{"asset_id": "nobody", "temperature": 7.0}]).encode()).json()
    assert rep2["quarantined"] == 1


def test_secrets_are_refused_in_connection_config(client, db_session):
    org_id, h = _org(client, db_session)
    r = client.post("/api/v1/data-sources", headers=h, json={
        "name": "leaky", "connector_type": "MQTT", "connection_config": {"broker": "x", "password": "hunter2"}})
    assert r.status_code == 422
    r = client.post("/api/v1/data-sources", headers=h, json={
        "name": "leaky2", "connector_type": "MQTT", "connection_config": {"auth": {"api_key": "k"}}})
    assert r.status_code == 422


def test_ingest_requires_flight_telemetry_entitlement(client, db_session):
    from app.core.security import hash_password
    from app.models.organization import Organization
    from app.models.user import User, UserRole
    from tests.integration.conftest import grant_features

    org = Organization(name=f"nofeat-{uuid.uuid4().hex[:6]}")
    db_session.add(org); db_session.flush()
    grant_features(db_session, org.id, "drone_fleet_management")       # telemetry NOT included
    u = User(organization_id=org.id, email=f"nf-{uuid.uuid4().hex[:6]}@example.com",
             hashed_password=hash_password(PW), full_name="N", is_active=True, email_verified=True)
    db_session.add(u); db_session.flush()
    db_session.add(UserRole(user_id=u.id, role_name="ORG_ADMIN", organization_id=org.id))
    db_session.commit()
    tok = client.post("/api/v1/auth/login", json={"email": u.email, "password": PW}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post(f"/api/v1/data-sources/{uuid.uuid4()}/ingest", headers=h, content=b"x")
    assert r.status_code == 403


def test_payload_limits(client, db_session, monkeypatch):
    org_id, h = _org(client, db_session)
    sid = _source(client, h, "CSV_BATCH")
    assert _ingest(client, h, sid, b"").status_code == 422
    import app.api.v1.data_sources as ds_api

    monkeypatch.setattr(ds_api, "MAX_INGEST_BYTES", 10)
    assert _ingest(client, h, sid, b"x" * 50).status_code == 413


# ------------------------------------------------------------------ isolation of failures + health
def test_one_failing_event_does_not_abort_the_rest(client, db_session, monkeypatch):
    org_id, h = _org(client, db_session)
    a = _drone(client, h, reg="F-1")
    sid = _source(client, h, "JSON_BATCH")
    real = acquisition_service.telemetry_service.process_normalized_event
    calls = {"n": 0}

    def flaky(db, *, organization_id, event, **kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("boom")
        return real(db, organization_id=organization_id, event=event, **kw)

    monkeypatch.setattr(acquisition_service.telemetry_service, "process_normalized_event", flaky)
    body = json.dumps([{"asset_id": "F-1", "temperature": float(i), "timestamp": f"2026-01-01T00:00:0{i}Z"} for i in range(4)]).encode()
    rep = _ingest(client, h, sid, body).json()
    assert rep["accepted"] == 3 and rep["failed"] == 1
    assert _readings(db_session, org_id, a) == 3
    health = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert health["error_count"] == 1


def test_health_evidence_transitions(client, db_session):
    org_id, h = _org(client, db_session)
    _drone(client, h, reg="H-1")
    sid = _source(client, h, "CSV_BATCH", {"expected_interval_seconds": 60})
    health = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert health["status"] == "HEALTHY" and health["reason"] == "NO_DATA_YET" and health["last_seen_at"] is None
    for _ in range(2):                                            # failures: nothing parseable
        _ingest(client, h, sid, b"asset_id,value\n,\n")
    assert client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()["status"] == "DEGRADED"
    for _ in range(3):
        _ingest(client, h, sid, b"asset_id,value\n,\n")
    failed = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert failed["status"] == "FAILED" and failed["last_failure_at"] and failed["last_error"]
    good = _csv([{"asset_id": "H-1", "sensor_code": "T", "value": "1", "unit": "C", "timestamp": "2026-01-01T00:00:00Z"}])
    assert _ingest(client, h, sid, good).json()["accepted"] == 1
    assert client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()["status"] == "HEALTHY"


def test_staleness_and_loss_and_quarantine_degrade_health(db_session):
    now = datetime.now(UTC)
    src = DataSource(organization_id=uuid.uuid4(), name="x", connector_type="MAVLINK", status="ACTIVE",
                     connection_config={"expected_interval_seconds": 10}, consecutive_failures=0,
                     total_events_ingested=100, total_events_rejected=0, total_events_duplicate=0,
                     total_events_quarantined=0, total_packets_lost=0, created_at=now - timedelta(days=1))
    src.last_success_at = now - timedelta(seconds=45)            # > 3x interval
    assert acquisition_service.compute_health_detail(src, now)["status"] == "DEGRADED"
    src.last_success_at = now - timedelta(seconds=500)           # > 10x interval
    assert acquisition_service.compute_health_detail(src, now)["status"] == "FAILED"
    src.last_success_at = now
    assert acquisition_service.compute_health_detail(src, now)["status"] == "HEALTHY"
    src.total_packets_lost = 60                                  # 60/(100+60)=37%
    d = acquisition_service.compute_health_detail(src, now)
    assert d["status"] == "DEGRADED" and "packet loss" in d["reason"]
    src.total_packets_lost = 0
    src.total_events_quarantined = 200
    assert "quarantined" in acquisition_service.compute_health_detail(src, now)["reason"]
    src.status = "PAUSED"
    assert acquisition_service.compute_health_detail(src, now)["status"] == "INACTIVE"


def test_mid_batch_vibration_spike_is_still_detected_with_batched_evaluation(client, db_session):
    """Batch ingestion evaluates HUMS every STRIDE readings (not per event). A spike in the middle of a large
    batch, followed by many normal readings, must still produce an exceedance."""
    from app.models.hums import HUMSExceedance

    org_id, h = _org(client, db_session)
    a1 = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": a1}})
    frames, seq = heartbeat(seq=1), 1
    for i in range(80):
        seq += 1
        frames += vibration(45.0, 52.0, 48.0, seq=seq) if i == 33 else vibration(1.5, 1.6, 1.7, seq=seq)
    rep = _ingest(client, h, sid, frames).json()
    assert rep["accepted"] >= 80
    n = db_session.scalar(select(func.count(HUMSExceedance.id)).where(
        HUMSExceedance.organization_id == org_id, HUMSExceedance.asset_id == uuid.UUID(a1)))
    assert n >= 1
