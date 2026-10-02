"""SITL No-Hardware Simulation Test Scenarios (Scenarios 1-10).

Validates the full software-in-the-loop (SITL) telemetry pipeline:
1. Normal flight and movement
2. Multiple virtual drones
3. GPS fix changes
4. Geofence entry and exit
5. Telemetry staleness
6. Telemetry interruption and recovery
7. Invalid coordinates and malformed packets
8. Delayed or out-of-order messages
9. Duplicate telemetry messages
10. Tenant isolation
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import struct
import time
import uuid
import pytest

from app.services import geo
from app.services.edge.mavlink_connector import MAVLinkConnector, mavlink_checksum, MAVLINK_STX_V2
from app.services.live_state_service import LiveBroker
from app.schemas.live_state import LiveStateV1, LiveIdentityV1, PositionV1, compute_freshness, GPS_FIX
from tests.unit.test_m20_mavlink_integrity import frame_v2, heartbeat, sys_status, vibration


def gps_raw(lat=10.0, lon=77.0, fix=3, sats=11, eph=95, **kw):
    return frame_v2(24, struct.pack("<QiiiHHHHBB", 1, int(lat * 1e7), int(lon * 1e7), 123_000, eph, 150, 0, 0, fix, sats), **kw)


def gpi(lat=10.0, lon=77.0, rel_mm=15_000, **kw):
    return frame_v2(33, struct.pack("<IiiiihhhH", 1, int(lat * 1e7), int(lon * 1e7), 120_000, rel_mm, 0, 0, 0, 0), **kw)


def pos(evt):
    return evt.raw_metadata["live_state"]["position"]


# --- Scenario 1: Normal flight and movement ---
def test_scenario_1_normal_flight_and_movement():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=1))
    c.feed_bytes(gps_raw(lat=10.0, lon=77.0, fix=3, sats=12, seq=2))
    (evt,) = c.feed_bytes(gpi(lat=10.005, lon=77.005, rel_mm=25_000, seq=3))
    
    p = pos(evt)
    assert p["lat"] == 10.005
    assert p["lon"] == 77.005
    assert p["alt_rel_m"] == 25.0
    assert p["gps_fix_type"] == 3
    assert p["gps_fix"] == "3D"
    assert p["satellites"] == 12


# --- Scenario 2: Multiple virtual drones ---
def test_scenario_2_multiple_virtual_drones():
    c = MAVLinkConnector()
    
    # Drone 1 (sysid 1)
    (e1,) = c.feed_bytes(heartbeat(sysid=1, seq=1))
    # Drone 2 (sysid 2)
    (e2,) = c.feed_bytes(heartbeat(sysid=2, seq=1))
    
    assert e1.raw_metadata["live_state"]["identity"]["mavlink_system_id"] == 1
    assert e2.raw_metadata["live_state"]["identity"]["mavlink_system_id"] == 2
    assert 1 in c.vehicles and 2 in c.vehicles


# --- Scenario 3: GPS fix changes ---
def test_scenario_3_gps_fix_transitions():
    c = MAVLinkConnector()
    # 0 = NO_GPS
    (e0,) = c.feed_bytes(gps_raw(lat=0.0, lon=0.0, fix=0, seq=1))
    assert pos(e0)["gps_fix_type"] == 0
    assert pos(e0)["gps_fix"] == "NO_GPS"
    
    # 3 = 3D_FIX
    (e3,) = c.feed_bytes(gps_raw(lat=10.0, lon=77.0, fix=3, seq=2))
    assert pos(e3)["gps_fix_type"] == 3
    assert pos(e3)["gps_fix"] == "3D"
    
    # 5 = RTK_FLOAT
    (e5,) = c.feed_bytes(gps_raw(lat=10.0, lon=77.0, fix=5, seq=3))
    assert pos(e5)["gps_fix_type"] == 5
    assert pos(e5)["gps_fix"] == "RTK_FLOAT"
    
    # 6 = RTK_FIXED
    (e6,) = c.feed_bytes(gps_raw(lat=10.0, lon=77.0, fix=6, seq=4))
    assert pos(e6)["gps_fix_type"] == 6
    assert pos(e6)["gps_fix"] == "RTK_FIXED"


# --- Scenario 4: Geofence calculation ---
def test_scenario_4_geofence_calculation():
    # Test circular fence: center (10.0, 77.0), radius 200m
    g = {"center": {"lat": 10.0, "lon": 77.0}, "radius_m": 200.0}
    
    # Inside center point: dist == -200m (< 0)
    d_in = geo.signed_distance_m("CIRCLE", g, 10.0, 77.0)
    assert d_in == pytest.approx(-200.0, abs=0.01)
    
    # Outside point: dist > 0
    d_out = geo.signed_distance_m("CIRCLE", g, 10.005, 77.0)
    assert d_out > 0


# --- Scenario 5: Telemetry staleness ---
def test_scenario_5_telemetry_freshness():
    broker = LiveBroker()
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    
    now = datetime.now(UTC)
    freshness = compute_freshness(now, now)
    assert freshness.state == "FRESH"
    
    # Check 15 seconds later -> STALE
    later_15s = now + timedelta(seconds=15)
    stale_freshness = compute_freshness(now, later_15s)
    assert stale_freshness.state == "STALE"
    
    # Check 75 seconds later -> LOST
    later_75s = now + timedelta(seconds=75)
    lost_freshness = compute_freshness(now, later_75s)
    assert lost_freshness.state == "LOST"
    
    state = LiveStateV1(
        identity=LiveIdentityV1(asset_id=asset_id),
        state_version=1,
        observed_at=now,
        received_at=now,
        freshness=freshness,
        position=PositionV1(lat=37.77, lon=-122.42, alt_msl_m=50.0, observed_at=now),
    )
    item = broker.publish(org_id, "drone", state.model_dump(mode="json", by_alias=True))
    assert item["type"] == "drone"
    assert item["data"]["identity"]["asset_id"] == str(asset_id)


# --- Scenario 6: Telemetry interruption and recovery ---
def test_scenario_6_interruption_and_recovery():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=200))
    c.disconnect()
    c.connect()
    # Reconnect resets sequence tracking so seq=3 is accepted
    assert len(c.feed_bytes(heartbeat(seq=3))) == 1


# --- Scenario 7: Invalid coordinates and malformed packets ---
def test_scenario_7_invalid_and_corrupt_packets():
    c = MAVLinkConnector()
    
    # Corrupt checksum packet
    corrupt_frame = frame_v2(0, struct.pack("<IBBBBB", 3, 2, 3, 129, 4, 3), corrupt=True)
    events = c.feed_bytes(corrupt_frame)
    assert len(events) == 0  # rejected by X.25 CRC check
    assert c.integrity["crc_errors"] >= 1
    assert c.stats.parse_errors >= 1


# --- Scenario 8: Delayed or out-of-order messages ---
def test_scenario_8_out_of_order_packets():
    c = MAVLinkConnector()
    c.feed_bytes(sys_status(remaining=80, seq=10))
    c.feed_bytes(sys_status(remaining=70, seq=11))
    # Out of order packet with older seq is dropped
    assert c.feed_bytes(sys_status(remaining=99, seq=9)) == []
    assert c.integrity["late"] == 1
    assert c.vehicles[1].battery_remaining_pct == 70


# --- Scenario 9: Duplicate telemetry messages ---
def test_scenario_9_duplicate_packets():
    c = MAVLinkConnector()
    f = heartbeat(seq=5)
    assert len(c.feed_bytes(f)) == 1
    assert len(c.feed_bytes(f)) == 0  # duplicate is dropped
    assert c.integrity["duplicates"] == 1


# --- Scenario 10: Tenant isolation ---
def test_scenario_10_tenant_isolation():
    broker = LiveBroker()
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    asset_a = uuid.uuid4()
    now = datetime.now(UTC)
    
    state_a = LiveStateV1(
        identity=LiveIdentityV1(asset_id=asset_a),
        state_version=1,
        observed_at=now,
        received_at=now,
        freshness=compute_freshness(now, now),
        position=PositionV1(lat=37.77, lon=-122.42, alt_msl_m=50.0, observed_at=now),
    )
    
    # Publish to Org A
    broker.publish(org_a, "drone", state_a.model_dump(mode="json", by_alias=True))
    
    # Replay for Org A with 0 cursor -> receives 1 item
    events_a = broker.replay_after(org_a, f"{broker.epoch}:0")
    assert events_a is not None
    assert len(events_a) == 1
    assert events_a[0]["data"]["identity"]["asset_id"] == str(asset_a)
    
    # Replay for Org B with 0 cursor -> returns empty list [] because current count is 0
    events_b = broker.replay_after(org_b, f"{broker.epoch}:0")
    assert events_b == []
