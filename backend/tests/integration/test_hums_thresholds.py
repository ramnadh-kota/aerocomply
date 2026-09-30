"""Per-sensor HUMS vibration limits: configured limits drive exceedances, health and prognostics; defaults unchanged;
validation, RBAC, tenant isolation, and an audit trail with the previous values."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.audit_event import AuditEvent
from app.models.hums import HUMSExceedance
from tests.integration.conftest import grant_features
from tests.integration.test_acquisition_pipeline import _drone, _org


def _readings(values, start_minutes_ago=30):
    base = datetime.now(UTC) - timedelta(minutes=start_minutes_ago)
    return {"readings": [{"recorded_at": (base + timedelta(seconds=i)).isoformat(), "value": v, "unit": "mm/s"}
                         for i, v in enumerate(values)]}


@pytest.fixture
def sensor_env(client, db_session):
    org_id, h = _org(client, db_session, "thr")
    grant_features(db_session, org_id, "drone_fleet_management", "hums", suite_code="DRONE_UAV")
    asset = _drone(client, h, reg="THR-1")
    r = client.post("/api/v1/hums/sensors", headers=h, json={
        "asset_id": asset, "sensor_code": "V1", "sensor_type": "ACCELEROMETER",
        "measurement_type": "vibration", "unit": "mm/s"})
    assert r.status_code == 200, r.text
    return org_id, h, asset, r.json()["id"]


def _exceedances(db, org_id, sensor_id):
    return db.execute(select(HUMSExceedance).where(
        HUMSExceedance.organization_id == org_id, HUMSExceedance.sensor_id == uuid.UUID(sensor_id))).scalars().all()


def test_platform_defaults_are_unchanged_when_nothing_is_configured(client, db_session, sensor_env):
    org_id, h, asset, sid = sensor_env
    assert client.get("/api/v1/hums/sensors", headers=h).json()[0]["warning_threshold"] is None
    assert client.post(f"/api/v1/hums/sensors/{sid}/readings", headers=h, json=_readings([6.0] * 20)).status_code == 200
    (exc,) = _exceedances(db_session, org_id, sid)
    assert (exc.severity, exc.threshold_value) == ("HIGH", 5.0)            # default warning limit


def test_configured_limits_replace_the_defaults_for_that_sensor_only(client, db_session, sensor_env):
    org_id, h, asset, sid = sensor_env
    other = client.post("/api/v1/hums/sensors", headers=h, json={
        "asset_id": asset, "sensor_code": "V2", "sensor_type": "ACCELEROMETER",
        "measurement_type": "vibration", "unit": "mm/s"}).json()["id"]
    r = client.put(f"/api/v1/hums/sensors/{sid}/thresholds", headers=h, json={"warning_threshold": 20, "critical_threshold": 40})
    assert r.status_code == 200 and (r.json()["warning_threshold"], r.json()["critical_threshold"]) == (20, 40)

    client.post(f"/api/v1/hums/sensors/{sid}/readings", headers=h, json=_readings([6.0] * 20))     # below 20: quiet
    assert _exceedances(db_session, org_id, sid) == []
    client.post(f"/api/v1/hums/sensors/{other}/readings", headers=h, json=_readings([6.0] * 20))   # default sensor: exceeds
    assert len(_exceedances(db_session, org_id, other)) == 1

    client.post(f"/api/v1/hums/sensors/{sid}/readings", headers=h, json=_readings([25.0] * 20, 10))
    (high,) = _exceedances(db_session, org_id, sid)
    assert (high.severity, high.threshold_value) == ("HIGH", 20.0)
    client.post(f"/api/v1/hums/sensors/{sid}/readings", headers=h, json=_readings([45.0] * 20, 5))
    crit = [e for e in _exceedances(db_session, org_id, sid) if e.severity == "CRITICAL"]
    assert crit and crit[0].threshold_value == 40.0

    health = client.get(f"/api/v1/hums/assets/{asset}/health", headers=h).json()
    assert health is not None
    from app.models.evidence import Evidence
    ev = db_session.execute(select(Evidence).where(Evidence.organization_id == org_id,
                                                   Evidence.asset_id == uuid.UUID(asset))).scalars().all()
    assert {e.provenance["threshold_source"] for e in ev if e.provenance and e.provenance.get("sensor_id") == sid} == {"CONFIGURED"}


def test_health_status_follows_the_configured_limits(client, db_session, sensor_env):
    org_id, h, asset, sid = sensor_env
    client.post(f"/api/v1/hums/sensors/{sid}/readings", headers=h, json=_readings([9.0] * 20))
    comp = lambda: next(c for c in client.get(f"/api/v1/hums/assets/{asset}/health", headers=h).json()["components"]  # noqa: E731
                        if c["sensor_id"] == sid)
    assert comp()["status"] == "CRITICAL"                                   # 9.0 >= default critical 8.0
    client.put(f"/api/v1/hums/sensors/{sid}/thresholds", headers=h, json={"warning_threshold": 30, "critical_threshold": 60})
    assert comp()["status"] == "HEALTHY"                                    # same data, OEM limits say fine


def test_validation_clearing_audit_rbac_and_isolation(client, db_session, sensor_env):
    org_id, h, asset, sid = sensor_env
    url = f"/api/v1/hums/sensors/{sid}/thresholds"
    for bad in ({"warning_threshold": 5}, {"critical_threshold": 8}, {"warning_threshold": 8, "critical_threshold": 5},
                {"warning_threshold": 5, "critical_threshold": 5}, {"warning_threshold": -1, "critical_threshold": 3},
                {"warning_threshold": 0, "critical_threshold": 3}, {"warning_threshold": "x", "critical_threshold": 3}):
        assert client.put(url, headers=h, json=bad).status_code == 422, bad
    assert client.put(url, headers=h, content=b'{"warning_threshold": NaN, "critical_threshold": 3}',
                      ).status_code == 422

    assert client.put(url, headers=h, json={"warning_threshold": 12, "critical_threshold": 24}).status_code == 200
    assert client.put(url, headers=h, json={"warning_threshold": 15, "critical_threshold": 30}).status_code == 200
    cleared = client.put(url, headers=h, json={"warning_threshold": None, "critical_threshold": None}).json()
    assert cleared["warning_threshold"] is None and cleared["critical_threshold"] is None
    trail = [a.event_metadata for a in db_session.execute(select(AuditEvent).where(
        AuditEvent.organization_id == org_id, AuditEvent.action == "hums_sensor.thresholds_set")).scalars()]
    assert len(trail) == 3
    assert {"previous": {"warning_threshold": 12.0, "critical_threshold": 24.0},
            "new": {"warning_threshold": 15.0, "critical_threshold": 30.0}} in trail

    _, other = _org(client, db_session, "thr2")
    assert client.put(url, headers=other, json={"warning_threshold": 1, "critical_threshold": 2}).status_code in (403, 404)
    grant_features(db_session, uuid.UUID(client.get("/api/v1/auth/me", headers=other).json()["organization_id"]),
                   "drone_fleet_management", "hums", suite_code="DRONE_UAV")
    assert client.put(url, headers=other, json={"warning_threshold": 1, "critical_threshold": 2}).status_code == 404
    assert client.put(url, json={"warning_threshold": 1, "critical_threshold": 2}).status_code == 401


def test_database_constraint_rejects_inconsistent_limits(db_session, client, sensor_env):
    org_id, h, asset, sid = sensor_env
    for bad in ("warning_threshold = 5, critical_threshold = NULL", "warning_threshold = 9, critical_threshold = 3",
                "warning_threshold = 0, critical_threshold = 3"):
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.execute(text(f"UPDATE hums_sensors SET {bad} WHERE id = :i"), {"i": sid})


def test_configured_critical_limit_is_the_prognostic_threshold():
    from app.models.hums import HUMSSensor
    from app.services.hums import prognostic_service as ps

    s = HUMSSensor(warning_threshold=20.0, critical_threshold=55.0)
    assert ps._get_threshold("rms", None, s) == (55.0, "MAINTENANCE_THRESHOLD")
    assert ps._get_threshold("rms", None, HUMSSensor())[0] == 8.0            # default unchanged
    assert ps._get_threshold("rms", None)[0] == 8.0
