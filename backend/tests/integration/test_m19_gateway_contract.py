"""M19.1 Contract Tests: Gateway Heartbeat & Ingestion compatibility with FastAPI backend."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.telemetry import EdgeDevice
from app.schemas.edge_hardware import EdgeDeviceHeartbeatRequest, EdgeDeviceHeartbeatResponse
from gateway.config import GatewayConfig
from gateway.health import get_gateway_health_payload
from tests.integration.test_c2_device_enrollment import _provision
from tests.integration.test_acquisition_pipeline import _org

K = "X-Kota-Device-Key"


def test_gateway_health_payload_matches_schema_and_backend_contract(client, db_session):
    """Phase 1 Contract Test: Gateway-generated payload must strictly conform to EdgeDeviceHeartbeatRequest

    and succeed against POST /api/v1/device/heartbeat.
    """
    _, h = _org(client, db_session, "m19hb1")
    dev_id, token = _provision(client, h)

    queue_stats = {
        "total_items": 42,
        "total_bytes": 1048576,
        "pending_items": 15,
        "in_flight_items": 5,
        "quarantined_items": 0,
    }
    start_time = time.time() - 3600.0

    # 1. Generate payload via gateway health module
    payload = get_gateway_health_payload(
        device_id=dev_id,
        queue_stats=queue_stats,
        start_time=start_time,
        software_version="1.2.0-rc1",
        connectivity_state="ONLINE",
    )

    # 2. Pydantic schema validation contract check
    parsed_req = EdgeDeviceHeartbeatRequest.model_validate(payload)
    assert parsed_req.device_id == dev_id
    assert parsed_req.queue_depth == 15
    assert parsed_req.connectivity_state == "ONLINE"
    assert parsed_req.software_version == "1.2.0-rc1"
    assert parsed_req.uptime_seconds is not None and parsed_req.uptime_seconds >= 3599
    assert isinstance(parsed_req.timestamp, datetime)

    # 3. Live FastAPI endpoint invocation
    resp = client.post(
        "/api/v1/device/heartbeat",
        headers={K: token},
        json=payload,
    )
    assert resp.status_code == 200, f"Heartbeat failed: {resp.text}"
    body = resp.json()
    assert body["status"] == "ACK"
    assert "server_time" in body
    assert "pending_commands_count" in body

    # 4. Verify DB persistence and observability update
    d = db_session.query(EdgeDevice).filter_by(device_id=dev_id).one()
    assert d.last_heartbeat_at is not None
    obs = (d.metadata_json or {}).get("observability", {})
    assert obs.get("queue_depth") == 15
    assert obs.get("uptime_seconds") >= 3599
    assert obs.get("connectivity_state") == "ONLINE"


def test_heartbeat_device_id_mismatch_rejected(client, db_session):
    """Verify that heartbeat with mismatched device_id is rejected with 403 Forbidden."""
    _, h = _org(client, db_session, "m19hb2")
    dev_id, token = _provision(client, h)

    payload = get_gateway_health_payload(
        device_id="spoofed-device-id",
        queue_stats={"pending_items": 2},
    )

    resp = client.post(
        "/api/v1/device/heartbeat",
        headers={K: token},
        json=payload,
    )
    assert resp.status_code == 403
    assert "does not match" in resp.text


def test_heartbeat_invalid_credentials_rejected(client, db_session):
    """Verify that heartbeat with invalid credentials is rejected with 401 Unauthorized."""
    _, h = _org(client, db_session, "m19hb3")
    dev_id, token = _provision(client, h)

    payload = get_gateway_health_payload(
        device_id=dev_id,
        queue_stats={"pending_items": 0},
    )

    # Missing header
    assert client.post("/api/v1/device/heartbeat", json=payload).status_code == 401

    # Malformed key
    assert client.post("/api/v1/device/heartbeat", headers={K: "invalid"}, json=payload).status_code == 401

    # Wrong secret
    tampered = token[:-4] + "ffff"
    assert client.post("/api/v1/device/heartbeat", headers={K: tampered}, json=payload).status_code == 401


def test_gateway_config_device_id_handling():
    """Verify GatewayConfig loads and preserves explicit device_id."""
    cfg = GatewayConfig(
        device_id="custom-companion-01",
        device_key="kdev.00000000-0000-0000-0000-000000000001.mysecret1234567890abcdef",
    )
    assert cfg.device_id == "custom-companion-01"

    env_cfg = GatewayConfig.from_env({
        "KOTA_DEVICE_ID": "companion-from-env",
        "KOTA_DEVICE_KEY": "kdev.00000000-0000-0000-0000-000000000002.mysecret1234567890abcdef",
    })
    assert env_cfg.device_id == "companion-from-env"
