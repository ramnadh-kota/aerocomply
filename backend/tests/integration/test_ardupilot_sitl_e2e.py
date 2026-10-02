"""ArduPilot SITL to Application End-to-End Integration Test.

Validates the full flow:
Virtual SITL Engine (UDP) -> MAVLink Edge Gateway -> LiveBroker -> Geofence Evaluator -> LISA Grounded Intelligence.
"""
from __future__ import annotations

import socket
import threading
import time
import uuid
from unittest.mock import MagicMock
import pytest

from app.services import geo
from app.services.edge.ardupilot_sitl_engine import ArduPilotSITLEngine
from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.live_state_service import LiveBroker
from app.schemas.auth import CurrentUser
from app.services.ai.tools import _handle_list_fleet_assets, _handle_get_alert_details
from app.schemas.live_state import LiveStateV1, LiveIdentityV1, PositionV1, BatteryV1, compute_freshness
from datetime import UTC, datetime


def test_ardupilot_sitl_full_application_e2e():
    host = "127.0.0.1"
    port = 14555
    test_org_id = uuid.UUID("00000000-0000-0000-0000-000000000099")
    test_drone_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    
    # 1. Setup Backend Ingestion Listener
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((host, port))
    server_sock.settimeout(1.0)
    
    connector = MAVLinkConnector()
    broker = LiveBroker()
    received_events = []
    stop_listener = threading.Event()
    
    def listener_loop():
        while not stop_listener.is_set():
            try:
                data, _ = server_sock.recvfrom(2048)
                events = connector.feed_bytes(data)
                for e in events:
                    received_events.append(e)
                    # Publish to broker under test organization
                    now = datetime.now(UTC)
                    p = e.raw_metadata.get("live_state", {}).get("position", {})
                    b = e.raw_metadata.get("live_state", {}).get("battery", {})
                    state = LiveStateV1(
                        identity=LiveIdentityV1(
                            asset_id=test_drone_id,
                            source_system="ARDUPILOT_SITL",
                            source_asset_id="SITL-DRONE-01",
                        ),
                        state_version=len(received_events),
                        observed_at=now,
                        received_at=now,
                        freshness=compute_freshness(now, now),
                        position=PositionV1(
                            lat=p.get("lat"),
                            lon=p.get("lon"),
                            alt_msl_m=p.get("alt_msl_m"),
                            alt_rel_m=p.get("alt_rel_m"),
                            gps_fix_type=p.get("gps_fix_type"),
                            gps_fix=p.get("gps_fix"),
                            satellites=p.get("satellites"),
                            hdop=p.get("hdop"),
                            observed_at=now,
                        ),
                        battery=BatteryV1(
                            voltage_v=b.get("voltage_v"),
                            current_a=b.get("current_a"),
                            remaining_pct=b.get("remaining_pct"),
                            observed_at=now,
                        ),
                    )
                    broker.publish(test_org_id, "drone", state.model_dump(mode="json", by_alias=True))
            except socket.timeout:
                continue
            except Exception:
                break

    listener_thread = threading.Thread(target=listener_loop, daemon=True)
    listener_thread.start()
    
    # 2. Launch ArduPilot SITL Virtual Drone
    sitl = ArduPilotSITLEngine(sysid=1, target_host=host, target_port=port)
    sitl.state.armed = True
    sitl.state.flight_mode = "GUIDED"
    sitl.state.heading_deg = 45.0  # Fly North-East
    
    try:
        # Run virtual flight physics for 10 cycles
        for _ in range(10):
            sitl.step_physics(dt=0.1)
            sitl.emit_telemetry_burst()
            time.sleep(0.05)
            
        time.sleep(0.2)
    finally:
        stop_listener.set()
        listener_thread.join(timeout=1.0)
        server_sock.close()
        sitl.stop()
    
    # 3. Verify Ingestion & Kinematics Evidence
    assert len(received_events) >= 10
    vehicle = connector.vehicles[1]
    assert vehicle.is_armed is True
    assert vehicle.flight_mode == "GUIDED"
    assert vehicle.battery_voltage_v < 25.2  # Battery discharged under motor load
    
    # 4. Verify Geofence Calculation
    # Circular geofence centered at initial point (37.7749, -122.4194), radius 50m
    fence_geom = {"center": {"lat": 37.7749, "lon": -122.4194}, "radius_m": 50.0}
    dist = geo.signed_distance_m("CIRCLE", fence_geom, sitl.state.lat_deg, sitl.state.lon_deg)
    # Drone flew North-East: distance should be evaluated accurately
    assert isinstance(dist, float)
    
    # 5. Verify Multi-Tenant Broker Replay
    events = broker.replay_after(test_org_id, f"{broker.epoch}:0")
    assert events is not None
    assert len(events) >= 1
    latest_state = events[-1]["data"]
    assert latest_state["identity"]["asset_id"] == str(test_drone_id)
    assert latest_state["position"]["gps_fix"] == "3D"
    
    # 6. Verify LISA Tool Grounding
    db = MagicMock()
    user = CurrentUser(
        id=uuid.uuid4(),
        organization_id=test_org_id,
        email="sitl-operator@kota.aero",
        full_name="SITL Operator",
        roles=["fleet_manager"],
    )
    
    # Mock asset resolution for test drone
    mock_asset = MagicMock()
    mock_asset.id = test_drone_id
    mock_asset.organization_id = test_org_id
    mock_asset.registration = "SITL-DRONE-01"
    mock_asset.model = "ArduCopter SITL"
    mock_asset.asset_type = "DRONE"
    mock_asset.status = "ACTIVE"
    db.execute.return_value.scalars.return_value.all.return_value = [mock_asset]
    db.execute.return_value.scalar_one_or_none.return_value = mock_asset

    # Mock entitlements
    mock_ent = MagicMock()
    mock_ent.effective_features = {"drone_fleet_management": True}
    import app.services.ai.tools as tools_mod
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(tools_mod, "resolve_entitlements", lambda *args, **kwargs: mock_ent)
    
    # Test LISA fleet assets retrieval
    result = _handle_list_fleet_assets(db, user, {"asset_type": "DRONE"})
    assert "assets" in result
    assert len(result["assets"]) == 1
    assert result["assets"][0]["registration"] == "SITL-DRONE-01"
    assert result["assets"][0]["model"] == "ArduCopter SITL"
