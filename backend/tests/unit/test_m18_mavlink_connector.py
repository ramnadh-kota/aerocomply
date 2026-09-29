"""M18 Tech Guy 1: Unit Tests for MAVLink Connector & Normalizer."""

import struct
from datetime import UTC, datetime

import pytest

from app.schemas.telemetry import NormalizedTelemetryEvent
from app.services.edge.connector_base import ConnectorState
from app.services.edge.mavlink_connector import (
    MAVLinkConnector,
    MAVLinkVehicleState,
    MSG_ID_ATTITUDE,
    MSG_ID_GLOBAL_POSITION_INT,
    MSG_ID_HEARTBEAT,
    MSG_ID_SYS_STATUS,
    MSG_ID_VIBRATION,
)


def test_mavlink_connector_initialization():
    conn = MAVLinkConnector(
        connector_id="test_conn_01",
        source_system="KOTA_MAVLINK",
        asset_mapping_override={1: "UAV-ALPHA-01", 2: "UAV-BRAVO-02"},
    )
    assert conn.state == ConnectorState.DISCONNECTED
    assert conn.connect("udp:127.0.0.1:14550") is True
    assert conn.state == ConnectorState.CONNECTED
    assert conn.stats.protocol == "MAVLINK"


def test_mavlink_decode_heartbeat_and_sys_status():
    dispatched_events: list[NormalizedTelemetryEvent] = []
    conn = MAVLinkConnector(
        connector_id="test_conn_02",
        asset_mapping_override={1: "UAV-ALPHA-01"},
        on_event_callback=dispatched_events.append,
    )

    # 1. Decode HEARTBEAT (Armed, AUTO mode)
    evt_hb = conn.decode_message(
        "HEARTBEAT",
        {
            "sysid": 1,
            "base_mode": 128 + 1,  # Armed flag bit
            "custom_mode": 3,      # AUTO
            "autopilot": "ARDUPILOT",
        },
    )
    assert evt_hb is not None
    assert evt_hb.source_asset_id == "UAV-ALPHA-01"
    assert evt_hb.flight.notes is not None
    assert "Armed: True" in evt_hb.flight.notes
    assert "Mode: AUTO" in evt_hb.flight.notes

    # 2. Decode SYS_STATUS (Battery 22.8V, 14.5A, 92% remaining)
    evt_sys = conn.decode_message(
        "SYS_STATUS",
        {
            "sysid": 1,
            "voltage_battery": 22800,  # 22.8 V
            "current_battery": 1450,   # 14.5 A
            "battery_remaining": 92,
        },
    )
    assert evt_sys is not None
    assert evt_sys.battery.voltage_v == 22.8
    assert evt_sys.battery.health_percent == 92
    assert evt_sys.raw_metadata["battery_current_a"] == 14.5


def test_mavlink_decode_global_position_and_attitude():
    conn = MAVLinkConnector(connector_id="test_conn_03")

    # Decode GLOBAL_POSITION_INT (37.7749 N, -122.4194 W, 120.5m alt, 15.2 m/s groundspeed)
    evt_pos = conn.decode_message(
        "GLOBAL_POSITION_INT",
        {
            "sysid": 1,
            "lat": 377749000,
            "lon": -1224194000,
            "alt": 120500,        # 120.5 m MSL
            "relative_alt": 45000, # 45.0 m AGL
            "vx": 1200,            # 12.0 m/s
            "vy": 930,             # 9.3 m/s
            "hdg": 18000,          # 180.0 deg
        },
    )
    assert evt_pos is not None
    assert round(evt_pos.raw_metadata["latitude"], 4) == 37.7749
    assert round(evt_pos.raw_metadata["longitude"], 4) == -122.4194
    assert evt_pos.raw_metadata["altitude_m"] == 120.5
    assert evt_pos.raw_metadata["relative_alt_m"] == 45.0
    assert evt_pos.raw_metadata["heading_deg"] == 180.0
    assert evt_pos.raw_metadata["groundspeed_mps"] > 15.0

    # Decode ATTITUDE (Roll 5.2 deg, Pitch -2.1 deg)
    evt_att = conn.decode_message(
        "ATTITUDE",
        {
            "sysid": 1,
            "roll": 0.09075,   # ~ 5.2 deg
            "pitch": -0.03665, # ~ -2.1 deg
            "yaw": 3.14159,    # ~ 180 deg
        },
    )
    assert evt_att is not None
    assert round(evt_att.raw_metadata["roll_deg"], 1) == 5.2
    assert round(evt_att.raw_metadata["pitch_deg"], 1) == -2.1


def test_mavlink_decode_vibration_and_esc_telemetry():
    conn = MAVLinkConnector(connector_id="test_conn_04")

    # Decode VIBRATION
    evt_vib = conn.decode_message(
        "VIBRATION",
        {
            "sysid": 1,
            "vibration_x": 4.5,
            "vibration_y": 5.2,
            "vibration_z": 7.8,
        },
    )
    assert evt_vib is not None
    vib_readings = [r for r in evt_vib.readings if r.measurement_type == "vibration"]
    assert len(vib_readings) == 1
    assert vib_readings[0].value > 5.0
    assert vib_readings[0].unit == "mm/s"

    # Decode ESC_STATUS (RPM 5400, Temp 48 C)
    evt_esc = conn.decode_message(
        "ESC_STATUS",
        {
            "sysid": 1,
            "rpm": 5400,
            "temperature": 48.5,
            "current": 18.2,
            "voltage": 23.1,
        },
    )
    assert evt_esc is not None
    rpm_reading = next(r for r in evt_esc.readings if r.measurement_type == "rpm")
    assert rpm_reading.value == 5400.0
    temp_reading = next(r for r in evt_esc.readings if r.measurement_type == "temperature")
    assert temp_reading.value == 48.5


def test_mavlink_binary_frame_stream_parsing():
    """Tests byte-level parsing of MAVLink v2 binary packet streams."""
    conn = MAVLinkConnector(connector_id="test_conn_bin")

    # Construct MAVLink v2 HEARTBEAT binary frame
    # Header: STX(0xFD), len(9), incompat(0), compat(0), seq(1), sysid(1), compid(1), msgid(0, 0, 0)
    # Payload: custom_mode(3 uint32), type(2 uint8), autopilot(3 uint8), base_mode(129 uint8), sys_status(4 uint8), mav_ver(3 uint8)
    # Checksum: 2 bytes
    payload = struct.pack("<IBBBBB", 3, 2, 3, 129, 4, 3)
    header = struct.pack("<BBBBBBB3B", 0xFD, len(payload), 0, 0, 1, 1, 1, 0, 0, 0)
    from app.services.edge.mavlink_connector import mavlink_checksum

    crc = struct.pack("<H", mavlink_checksum(header[1:] + payload, 0))  # real checksum (HEARTBEAT)
    raw_packet = header + payload + crc

    # Feed in chunks (simulating serial/network streaming)
    events_1 = conn.feed_bytes(raw_packet[:5])
    assert len(events_1) == 0  # Incomplete packet

    events_2 = conn.feed_bytes(raw_packet[5:])
    assert len(events_2) == 1
    assert events_2[0].source_asset_id == "UAV-MAV-001"
    assert "Mode: AUTO" in events_2[0].flight.notes


def test_mavlink_multi_vehicle_isolation():
    conn = MAVLinkConnector(
        connector_id="test_conn_multi",
        asset_mapping_override={1: "UAV-ALPHA-01", 2: "UAV-BRAVO-02", 3: "UAV-CHARLIE-03"},
    )

    evt1 = conn.decode_message("HEARTBEAT", {"sysid": 1, "custom_mode": 3})
    evt2 = conn.decode_message("HEARTBEAT", {"sysid": 2, "custom_mode": 5})
    evt3 = conn.decode_message("HEARTBEAT", {"sysid": 3, "custom_mode": 6})

    assert evt1.source_asset_id == "UAV-ALPHA-01"
    assert evt2.source_asset_id == "UAV-BRAVO-02"
    assert evt3.source_asset_id == "UAV-CHARLIE-03"
    assert conn.stats.active_system_ids == [1, 2, 3]
