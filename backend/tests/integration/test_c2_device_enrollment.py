"""C2: device enrollment, credential auth, rotation, revocation, tenant isolation and connectivity."""
import uuid
from datetime import UTC, datetime, timedelta

from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org, _source
from tests.unit.test_m20_mavlink_integrity import vibration

K = "X-Kota-Device-Key"


def _provision(client, h, asset_id=None, device_id=None):
    device_id = device_id or f"companion-{uuid.uuid4().hex[:6]}"
    r = client.post("/api/v1/edge/devices/provision", headers=h, json={
        "device_id": device_id, "device_type": "EDGE_GATEWAY", "asset_id": asset_id})
    assert r.status_code == 201, r.text
    return device_id, r.json()["provisioning_token"]


def _hb(device_id):
    return {"device_id": device_id, "timestamp": datetime.now(UTC).isoformat()}


def test_credential_format_and_unauthenticated_rejected(client, db_session):
    _, h = _org(client, db_session, "c2a")
    dev, tok = _provision(client, h)
    assert tok.startswith("kdev.")
    for headers in ({}, {K: "garbage"}, {K: f"kdev.{uuid.uuid4()}.nope"}, {K: tok[:-2] + "xx"}, h):
        r = client.post("/api/v1/device/heartbeat", headers=headers, json=_hb(dev))
        assert r.status_code == 401, (headers, r.text)
    # a user JWT is not a device credential
    assert client.post("/api/v1/device/telemetry/mavlink", headers=h, content=b"x").status_code == 401


def test_heartbeat_and_connectivity(client, db_session):
    _, h = _org(client, db_session, "c2b")
    dev, tok = _provision(client, h)
    before = client.get(f"/api/v1/edge/devices/{dev}/connectivity", headers=h).json()
    assert before["connectivity"] == "OFFLINE" and before["telemetry_freshness"] == "NO_TELEMETRY"
    r = client.post("/api/v1/device/heartbeat", headers={K: tok}, json=_hb(dev))
    assert r.status_code == 200, r.text
    after = client.get(f"/api/v1/edge/devices/{dev}/connectivity", headers=h).json()
    assert after["connectivity"] == "ONLINE"
    # a heartbeat for ANOTHER device id with this credential is refused
    assert client.post("/api/v1/device/heartbeat", headers={K: tok}, json=_hb("other")).status_code == 403
    # timeout behaviour is evidence-based and configurable
    from app.models.telemetry import EdgeDevice
    from app.services.device_auth_service import connectivity_status

    d = db_session.query(EdgeDevice).filter_by(device_id=dev).one()
    late = datetime.now(UTC) + timedelta(seconds=100)       # default timeout 3 x 30s = 90s
    assert connectivity_status(d, late)["connectivity"] == "DEGRADED"
    assert connectivity_status(d, datetime.now(UTC) + timedelta(seconds=400))["connectivity"] == "OFFLINE"


def test_rotation_with_and_without_grace_and_revocation(client, db_session):
    _, h = _org(client, db_session, "c2c")
    dev, old = _provision(client, h)
    r = client.post(f"/api/v1/edge/devices/{dev}/credential/rotate", headers=h, json={"grace_seconds": 60})
    assert r.status_code == 200 and r.json()["credential_version"] == 2
    new = r.json()["credential"]
    assert client.post("/api/v1/device/heartbeat", headers={K: old}, json=_hb(dev)).status_code == 200  # in grace
    assert client.post("/api/v1/device/heartbeat", headers={K: new}, json=_hb(dev)).status_code == 200
    third = client.post(f"/api/v1/edge/devices/{dev}/credential/rotate", headers=h, json={}).json()["credential"]
    assert client.post("/api/v1/device/heartbeat", headers={K: new}, json=_hb(dev)).status_code == 401
    assert client.post("/api/v1/device/heartbeat", headers={K: third}, json=_hb(dev)).status_code == 200
    assert client.post(f"/api/v1/edge/devices/{dev}/revoke", headers=h, json={"reason": "lost device"}).status_code == 200
    assert client.post("/api/v1/device/heartbeat", headers={K: third}, json=_hb(dev)).status_code == 401
    assert client.post(f"/api/v1/edge/devices/{dev}/credential/rotate", headers=h, json={}).status_code == 409


def test_unauthorised_enrollment_and_tenant_isolation(client, db_session):
    _, h1 = _org(client, db_session, "c2d1")
    _, h2 = _org(client, db_session, "c2d2")
    assert client.post("/api/v1/edge/devices/provision", json={"device_id": "x"}).status_code in (401, 403)
    dev, tok = _provision(client, h1)
    # org 2 cannot see, rotate or bind org 1's device
    assert client.get(f"/api/v1/edge/devices/{dev}/connectivity", headers=h2).status_code == 404
    assert client.post(f"/api/v1/edge/devices/{dev}/credential/rotate", headers=h2, json={}).status_code == 404
    assert dev not in [d["device_id"] for d in client.get("/api/v1/edge/connectivity", headers=h2).json()]
    foreign_src = _source(client, h2, "MAVLINK")
    assert client.put(f"/api/v1/edge/devices/{dev}/data-source", headers=h1,
                      json={"data_source_id": foreign_src}).status_code == 404


def test_device_mavlink_upload_routes_into_bound_source_only(client, db_session):
    org_id, h = _org(client, db_session, "c2e")
    asset = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    dev, tok = _provision(client, h, asset_id=asset)
    # not bound yet
    r = client.post("/api/v1/device/telemetry/mavlink", headers={K: tok}, content=vibration(seq=1))
    assert r.status_code == 409 and r.json()["error"]["code"] == "device_not_bound"
    csv_src = _source(client, h, "CSV_BATCH")
    assert client.put(f"/api/v1/edge/devices/{dev}/data-source", headers=h,
                      json={"data_source_id": csv_src}).status_code == 409   # only MAVLINK sources bind
    assert client.put(f"/api/v1/edge/devices/{dev}/data-source", headers=h,
                      json={"data_source_id": sid}).status_code == 200
    r = client.post("/api/v1/device/telemetry/mavlink", headers={K: tok}, content=vibration(seq=1))
    assert r.status_code == 200 and r.json()["accepted"] == 1, r.text
    state = client.get(f"/api/v1/edge/devices/{dev}/connectivity", headers=h).json()
    assert state["telemetry_freshness"] == "FRESH" and state["data_source_id"] == sid
    assert _ingest(client, h, sid, vibration(seq=2)).status_code == 200      # user path unchanged
    # revoked devices can no longer upload
    client.post(f"/api/v1/edge/devices/{dev}/revoke", headers=h, json={"reason": "decommissioned"})
    assert client.post("/api/v1/device/telemetry/mavlink", headers={K: tok},
                       content=vibration(seq=3)).status_code == 401
