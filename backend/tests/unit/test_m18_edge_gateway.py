"""M18: Edge Gateway & Store-and-Forward Unit Tests.

Validates:
- Connector registration and canonical event buffering.
- Local FIFO buffering and capacity limits.
- Online batch flushing to Kota Cloud.
- Network interruption handling and offline queue retention.
- Reconnection and store-and-forward automatic replay.
- Server error recovery and FIFO preservation.
- Edge device heartbeat generation and observability metrics.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.schemas.edge_hardware import EdgeDeviceHeartbeatRequest
from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryReadingItem,
)
from app.services.edge.connector_base import ConnectorState
from app.services.edge.gateway_service import GatewayMetrics, KotaTelemetryGateway
from app.services.edge.mavlink_connector import MAVLinkConnector


def _make_mock_telemetry_event(
    asset_id: str = "UAV-KOTA-001",
    event_id: str = "EV-001",
    voltage: float = 24.5,
) -> NormalizedTelemetryEvent:
    return NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id=event_id,
        source_asset_id=asset_id,
        event_type="TELEMETRY_SAMPLE",
        event_timestamp=datetime.now(UTC),
        readings=[
            TelemetryReadingItem(
                sensor_code="BATT_VOLT",
                sensor_type="VOLTAGE",
                measurement_type="VOLTAGE",
                value=voltage,
                unit="V",
                data_quality="VALID",
            )
        ],
    )


def test_gateway_initialization_and_registration():
    gw = KotaTelemetryGateway(gateway_id="GW-UNIT-01", buffer_capacity=100, batch_size=10)
    assert gw.gateway_id == "GW-UNIT-01"
    assert gw.is_online is True
    assert len(gw.buffer) == 0

    connector = MAVLinkConnector(connector_id="MAV-TEST-01")
    gw.register_connector(connector)

    assert "MAV-TEST-01" in gw.connectors
    assert connector.on_event_callback == gw.ingest_event


def test_gateway_event_ingestion_and_buffering():
    gw = KotaTelemetryGateway(gateway_id="GW-UNIT-01", buffer_capacity=50)
    connector = MAVLinkConnector(connector_id="MAV-01")
    gw.register_connector(connector)

    for i in range(5):
        ev = _make_mock_telemetry_event(asset_id="UAV-ALPHA", event_id=f"EV-{i}")
        gw.ingest_event(ev)

    assert len(gw.buffer) == 5
    assert gw.metrics.events_received == 5
    assert gw.metrics.queue_depth == 5
    assert "UAV-ALPHA" in gw.metrics.active_vehicles


def test_gateway_flush_to_cloud_success():
    gw = KotaTelemetryGateway(gateway_id="GW-UNIT-01", buffer_capacity=100, batch_size=10)

    # Ingest 25 events
    for i in range(25):
        gw.ingest_event(_make_mock_telemetry_event(event_id=f"EV-{i}"))

    # Mock HTTP client
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "total_received": 10,
        "processed_count": 10,
        "duplicate_count": 0,
        "rejected_count": 0,
    }
    mock_client.post.return_value = mock_resp

    # First flush (10 events)
    res1 = gw.flush_to_cloud(http_client=mock_client)
    assert res1["status"] == "SUCCESS"
    assert res1["transmitted"] == 10
    assert res1["remaining"] == 15

    # Second flush (10 events)
    res2 = gw.flush_to_cloud(http_client=mock_client)
    assert res2["status"] == "SUCCESS"
    assert res2["transmitted"] == 10
    assert res2["remaining"] == 5

    assert gw.metrics.events_transmitted == 20


def test_gateway_offline_buffering_and_reconnect_sync():
    gw = KotaTelemetryGateway(gateway_id="GW-OFFLINE-01", buffer_capacity=100, batch_size=10)

    # Ingest while online
    gw.ingest_event(_make_mock_telemetry_event(event_id="EV-1"))
    assert len(gw.buffer) == 1

    # Simulate network failure during flush
    mock_client = MagicMock()
    mock_client.post.side_effect = Exception("Connection timeout / no cellular route")

    res = gw.flush_to_cloud(http_client=mock_client)
    assert res["status"] == "NETWORK_FAILURE"
    assert gw.is_online is False
    assert len(gw.buffer) == 1  # Retained in buffer

    # Ingest 15 more events while offline
    for i in range(2, 17):
        gw.ingest_event(_make_mock_telemetry_event(event_id=f"EV-{i}"))

    assert len(gw.buffer) == 16
    assert gw.is_online is False

    # Attempt flush while offline -> returns OFFLINE_BUFFERED
    off_res = gw.flush_to_cloud(http_client=mock_client)
    assert off_res["status"] == "OFFLINE_BUFFERED"
    assert off_res["remaining"] == 16

    # Restore connectivity and synchronize
    mock_client.post.side_effect = None
    
    def _mock_post(url, **kwargs):
        req_json = kwargs.get("json", {})
        num_ev = len(req_json.get("events", []))
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"processed_count": num_ev, "duplicate_count": 0}
        return resp

    mock_client.post.side_effect = _mock_post

    sync_res = gw.reconnect_and_sync(http_client=mock_client)
    assert sync_res["status"] == "SYNC_COMPLETE"
    assert sync_res["total_replayed"] == 16
    assert sync_res["remaining_queue"] == 0
    assert gw.is_online is True
    assert gw.metrics.events_replayed == 16


def test_gateway_server_error_and_batch_preservation():
    gw = KotaTelemetryGateway(gateway_id="GW-ERR-01", buffer_capacity=50, batch_size=5)

    for i in range(5):
        gw.ingest_event(_make_mock_telemetry_event(event_id=f"EV-ERR-{i}"))

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 503  # Cloud temporary maintenance
    mock_resp.json.return_value = {"error": "Service unavailable"}
    mock_client.post.return_value = mock_resp

    res = gw.flush_to_cloud(http_client=mock_client)
    assert res["status"] == "SERVER_ERROR"
    assert res["http_status"] == 503
    # The batch of 5 was returned to front of buffer
    assert len(gw.buffer) == 5
    assert gw.metrics.events_failed == 5


def test_gateway_buffer_overflow_fifo_eviction():
    gw = KotaTelemetryGateway(gateway_id="GW-CAP-01", buffer_capacity=3)

    ev1 = _make_mock_telemetry_event(event_id="EV-1")
    ev2 = _make_mock_telemetry_event(event_id="EV-2")
    ev3 = _make_mock_telemetry_event(event_id="EV-3")
    ev4 = _make_mock_telemetry_event(event_id="EV-4")

    gw.ingest_event(ev1)
    gw.ingest_event(ev2)
    gw.ingest_event(ev3)
    assert len(gw.buffer) == 3
    assert gw.buffer[0].source_event_id == "EV-1"

    # Ingest 4th -> evicts EV-1 (FIFO)
    gw.ingest_event(ev4)
    assert len(gw.buffer) == 3
    assert gw.buffer[0].source_event_id == "EV-2"
    assert gw.buffer[2].source_event_id == "EV-4"


def test_gateway_build_heartbeat_payload():
    gw = KotaTelemetryGateway(gateway_id="GW-HEARTBEAT-01")
    connector = MAVLinkConnector(connector_id="MAV-UAV-01")
    connector.state = ConnectorState.STREAMING
    gw.register_connector(connector)

    gw.ingest_event(_make_mock_telemetry_event(asset_id="UAV-01"))

    hb = gw.build_heartbeat_payload()
    assert isinstance(hb, EdgeDeviceHeartbeatRequest)
    assert hb.device_id == "GW-HEARTBEAT-01"
    assert hb.connectivity_state == "ONLINE"
    assert hb.sensor_states.get("MAV-UAV-01") == "VALID"
    assert hb.queue_depth == 1
    assert hb.observability.get("events_received") == 1
    assert "UAV-01" in hb.observability.get("active_uavs", [])
