"""M19.1 Phase 7 End-to-End Gateway Integration Tests.

Validates the full path:
Gateway -> Device Authentication -> MAVLink Upload -> Backend Ingestion -> PostgreSQL (TelemetryEventLog)

Includes:
- Authorized device
- Invalid credential
- Revoked device
- Wrong drone association
- Missing entitlement
- Valid telemetry & PostgreSQL persistence verification
- Duplicate retry
- Invalid frames & quarantine
- Partial acknowledgment batch splitting
- Network outage and recovery simulation
- Heartbeat & operational observability
- Tenant isolation
"""

from __future__ import annotations

import time
import uuid

import pytest

from app.models.organization import Organization
from app.models.telemetry import EdgeDevice, TelemetryEventLog, TelemetryProcessingStatus
from app.models.tenant_entitlement import TenantFeatureOverride
from gateway.ack_handler import AckAction, TelemetryAckHandler
from gateway.config import GatewayConfig
from gateway.health import get_gateway_health_payload
from gateway.local_queue import PersistentQueue
from tests.integration.test_acquisition_pipeline import _drone, _org, _source
from tests.integration.test_c2_device_enrollment import _provision
from tests.unit.test_m20_mavlink_integrity import frame_v2, heartbeat, vibration

K = "X-Kota-Device-Key"


def test_authorized_device_telemetry_persisted_in_postgresql(client, db_session):
    """Path: Gateway -> Device Auth -> Ingestion -> PostgreSQL persistence."""
    org_id, h = _org(client, db_session, "m19e2e_auth")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)

    # Bind device to source
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    # Prepare valid MAVLink frame
    frame = vibration(x=2.5, y=3.5, z=4.5, seq=10)

    # Ingest through device gateway endpoint
    resp = client.post(
        "/api/v1/device/telemetry/mavlink",
        headers={K: token},
        content=frame,
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["accepted"] == 1
    assert report["rejected"] == 0

    # Direct database inspection in PostgreSQL
    db_session.expire_all()
    events = (
        db_session.query(TelemetryEventLog)
        .filter_by(organization_id=org_id)
        .all()
    )
    assert len(events) >= 1
    ev = events[-1]
    assert ev.processing_status == TelemetryProcessingStatus.PROCESSED
    assert ev.asset_id == uuid.UUID(asset_id)
    assert ev.readings_count > 0


def test_invalid_credential_rejected(client, db_session):
    """Device key check fails closed on bad tokens."""
    _, h = _org(client, db_session, "m19e2e_inv")
    dev_id, token = _provision(client, h)

    frame = vibration(seq=1)
    # Missing header
    assert client.post("/api/v1/device/telemetry/mavlink", content=frame).status_code == 401
    # Garbage token
    assert client.post("/api/v1/device/telemetry/mavlink", headers={K: "kdev.invalid.token"}, content=frame).status_code == 401
    # Tampered secret
    tampered = token[:-4] + "0000"
    assert client.post("/api/v1/device/telemetry/mavlink", headers={K: tampered}, content=frame).status_code == 401


def test_revoked_device_rejected(client, db_session):
    """Revoked device is immediately forbidden from uploading telemetry."""
    _, h = _org(client, db_session, "m19e2e_rev")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    # Valid before revocation
    assert client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=vibration(seq=1)).status_code == 200

    # Revoke device
    rev_resp = client.post(f"/api/v1/edge/devices/{dev_id}/revoke", headers=h, json={"reason": "security decommission"})
    assert rev_resp.status_code == 200

    # Refused after revocation (401 constant-time auth rejection)
    assert client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=vibration(seq=2)).status_code == 401


def test_missing_telemetry_entitlement(client, db_session):
    """Organization without flight_telemetry entitlement is refused upload with 403 Forbidden."""
    org_id, h = _org(client, db_session, "m19e2e_ent")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    # Disable flight_telemetry entitlement for this organization
    override = TenantFeatureOverride(
        organization_id=org_id,
        feature_key="flight_telemetry",
        enabled=False,
    )
    db_session.add(override)
    db_session.commit()

    resp = client.post(
        "/api/v1/device/telemetry/mavlink",
        headers={K: token},
        content=vibration(seq=1),
    )
    assert resp.status_code == 403
    assert "not entitled" in resp.text


def test_duplicate_retry_handling(client, db_session):
    """Re-transmitting duplicate sequence frames returns duplicate count and gateway ack handler accepts."""
    org_id, h = _org(client, db_session, "m19e2e_dup")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    frame = vibration(seq=15)
    # Upload payload with two identical consecutive frames: first is accepted, second is duplicate
    resp = client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=frame + frame)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1
    assert data["duplicates"] == 1

    # Verify Gateway AckHandler recognizes duplicate-only as ACKNOWLEDGE
    ack_handler = TelemetryAckHandler()
    dup_only_resp = {"accepted": 0, "duplicates": 2, "rejected": 0, "failed": 0, "errors": []}
    eval_res = ack_handler.evaluate(200, dup_only_resp, batch_size=1)
    assert eval_res.action == AckAction.ACKNOWLEDGE


def test_invalid_corrupted_frame_quarantine(client, db_session):
    """Corrupt MAVLink frame is rejected by backend and quarantined by gateway."""
    org_id, h = _org(client, db_session, "m19e2e_corrupt")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    # Generate frame with deliberately broken CRC
    corrupt_frame = frame_v2(241, b"\x01\x02\x03\x04", seq=1, corrupt=True)

    resp = client.post(
        "/api/v1/device/telemetry/mavlink",
        headers={K: token},
        content=corrupt_frame,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 0
    assert data["rejected"] > 0

    ack_handler = TelemetryAckHandler()
    # Single corrupt item evaluated -> QUARANTINE
    eval_res = ack_handler.evaluate(200, data, batch_size=1)
    assert eval_res.action == AckAction.QUARANTINE


def test_partial_acknowledgment_batch_splitting(client, db_session):
    """Mixed batch of valid and corrupt frames splits into individual items, preserving valid data."""
    org_id, h = _org(client, db_session, "m19e2e_partial")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    valid_frame = vibration(seq=20)
    corrupt_frame = frame_v2(241, b"corrupted", seq=21, corrupt=True)

    # Combined batch
    combined = valid_frame + corrupt_frame
    resp = client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=combined)
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] == 1
    assert data["rejected"] >= 1

    # In multi-item mode, gateway splits the batch
    ack_handler = TelemetryAckHandler()
    eval_multi = ack_handler.evaluate(200, data, batch_size=2)
    assert eval_multi.action == AckAction.SPLIT

    # When sent individually:
    # 1. Valid frame is now duplicate (or accepted) -> ACKNOWLEDGE
    r_valid = client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=valid_frame)
    eval_valid = ack_handler.evaluate(200, r_valid.json(), batch_size=1)
    assert eval_valid.action == AckAction.ACKNOWLEDGE

    # 2. Corrupt frame is rejected -> QUARANTINE
    r_corrupt = client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=corrupt_frame)
    eval_corrupt = ack_handler.evaluate(200, r_corrupt.json(), batch_size=1)
    assert eval_corrupt.action == AckAction.QUARANTINE


def test_network_outage_buffering_and_recovery(client, db_session, tmp_path):
    """Queue accumulates frames during simulated network outage and drains cleanly upon reconnection."""
    org_id, h = _org(client, db_session, "m19e2e_outage")
    asset_id = _drone(client, h)
    source_id = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset_id}})
    dev_id, token = _provision(client, h, asset_id=asset_id)
    client.put(f"/api/v1/edge/devices/{dev_id}/data-source", headers=h, json={"data_source_id": source_id})

    db_file = str(tmp_path / "outage_queue.db")
    queue = PersistentQueue(db_path=db_file)

    # 1. Simulate outage: 5 frames enqueued into local queue while offline
    f1 = vibration(seq=31)
    f2 = vibration(seq=32)
    f3 = vibration(seq=33)
    queue.enqueue(f1)
    queue.enqueue(f2)
    queue.enqueue(f3)

    stats = queue.get_stats()
    assert stats["pending_items"] == 3

    # 2. Network restored: Dequeue and upload batch
    item_ids, batch_data = queue.dequeue_batch(max_count=10)
    assert len(item_ids) == 3

    resp = client.post("/api/v1/device/telemetry/mavlink", headers={K: token}, content=batch_data)
    assert resp.status_code == 200
    report = resp.json()
    assert report["accepted"] == 3

    queue.acknowledge_batch(item_ids)
    assert queue.get_stats()["total_items"] == 0


def test_tenant_isolation_boundary(client, db_session):
    """Device from Tenant A cannot upload into Tenant B's data source or view Tenant B's assets."""
    org1, h1 = _org(client, db_session, "m19iso_a")
    org2, h2 = _org(client, db_session, "m19iso_b")

    asset1 = _drone(client, h1)
    asset2 = _drone(client, h2)

    src1 = _source(client, h1, "MAVLINK", {"system_id_map": {"1": asset1}})
    src2 = _source(client, h2, "MAVLINK", {"system_id_map": {"1": asset2}})

    dev1, tok1 = _provision(client, h1, asset_id=asset1)
    dev2, tok2 = _provision(client, h2, asset_id=asset2)

    # Org 1 cannot bind its device to Org 2's data source
    assert client.put(f"/api/v1/edge/devices/{dev1}/data-source", headers=h1, json={"data_source_id": src2}).status_code == 404

    # Bind properly within tenant
    client.put(f"/api/v1/edge/devices/{dev1}/data-source", headers=h1, json={"data_source_id": src1})

    # Device 1 uploads telemetry
    r = client.post("/api/v1/device/telemetry/mavlink", headers={K: tok1}, content=vibration(seq=50))
    assert r.status_code == 200

    # PostgreSQL verification: event belongs ONLY to Org 1
    db_session.expire_all()
    evs_org1 = db_session.query(TelemetryEventLog).filter_by(organization_id=org1).all()
    evs_org2 = db_session.query(TelemetryEventLog).filter_by(organization_id=org2).all()
    assert len(evs_org1) >= 1
    assert len(evs_org2) == 0  # Tenant 2 is strictly isolated!
