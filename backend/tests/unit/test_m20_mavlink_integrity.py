"""M20: MAVLink acquisition integrity -- identity, ordering, dedup, corruption, loss.

Before M20 the connector (a) never verified the frame checksum, (b) parsed `seq` and
`compid` and then discarded them, (c) let any component (GCS sysid 255, gimbal,
companion computer) update a vehicle's state, and (d) emitted invented measurements
(battery 24 V / 99 %, cycle_count 15, vibration 1.8 mm/s) before the vehicle had sent
anything. These tests pin the corrected behaviour. Frames are built with the
connector's own `mavlink_checksum`; that helper and the CRC_EXTRA table were
cross-checked against the official pymavlink dialect definitions during development.
"""
from __future__ import annotations

import struct

from app.services.edge import mavlink_connector as mc
from app.services.edge.mavlink_connector import MAVLinkConnector, mavlink_checksum


def frame_v2(msgid: int, payload: bytes, *, seq: int = 0, sysid: int = 1, compid: int = 1,
             signed: bool = False, corrupt: bool = False) -> bytes:
    payload = payload.rstrip(b"\x00") or b"\x00"  # MAVLink v2 trims trailing zeros
    incompat = 1 if signed else 0
    header = struct.pack("<BBBBBBB", len(payload), incompat, 0, seq & 0xFF, sysid, compid, msgid & 0xFF) \
        + bytes([(msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF])
    crc = mavlink_checksum(header + payload, msgid)
    if corrupt:
        crc ^= 0x00FF
    out = bytes([mc.MAVLINK_STX_V2]) + header + payload + struct.pack("<H", crc)
    return out + (b"\x11" * 13 if signed else b"")


def heartbeat(**kw) -> bytes:
    return frame_v2(0, struct.pack("<IBBBBB", 3, 2, 3, 129, 4, 3), **kw)


def sys_status(volt_mv=24100, cur_ca=1500, remaining=87, **kw) -> bytes:
    # wire order: 3x uint32, then uint16/int16 x9 (load, voltage, current, drop, errors_comm, err1-4), then int8
    return frame_v2(1, struct.pack("<IIIHHhHHHHHHb", 0, 0, 0, 500, volt_mv, cur_ca, 0, 0, 0, 0, 0, 0, remaining), **kw)


def vibration(x=3.0, y=4.0, z=5.0, **kw) -> bytes:
    return frame_v2(241, struct.pack("<QfffIII", 1, x, y, z, 0, 0, 0), **kw)


def test_no_invented_measurements_from_a_bare_heartbeat():
    c = MAVLinkConnector()
    (evt,) = c.feed_bytes(heartbeat(seq=1))
    assert evt.battery is None          # was: 24 V / 99 % / cycle_count 15
    assert evt.readings == []           # was: VALID vibration 1.8 mm/s
    assert evt.raw_metadata["battery_current_a"] is None


def test_measurements_appear_only_after_the_vehicle_reports_them():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=1))
    (evt,) = c.feed_bytes(sys_status(seq=2))
    assert evt.battery.voltage_v == 24.1 and evt.battery.health_percent == 87
    assert evt.battery.cycle_count is None
    assert evt.readings == []
    (evt,) = c.feed_bytes(vibration(seq=3))
    assert [r.value for r in evt.readings] == [4.082]  # sqrt((9+16+25)/3)


def test_sys_status_battery_remaining_read_from_correct_offset():
    (evt,) = MAVLinkConnector().feed_bytes(sys_status(remaining=42, seq=1))
    assert evt.battery.health_percent == 42  # previously always 0


def test_corrupt_frame_rejected_and_stream_resynchronises():
    c = MAVLinkConnector()
    bad = heartbeat(seq=1, corrupt=True)
    events = c.feed_bytes(bad + heartbeat(seq=2))
    assert len(events) == 1                       # only the valid frame
    assert c.integrity["crc_errors"] >= 1
    assert c.stats.parse_errors >= 1


def test_garbage_bytes_are_skipped():
    c = MAVLinkConnector()
    assert len(c.feed_bytes(b"\x00\x01\x02garbage" + heartbeat(seq=1))) == 1


def test_duplicate_frame_is_dropped():
    c = MAVLinkConnector()
    f = heartbeat(seq=5)
    assert len(c.feed_bytes(f)) == 1
    assert len(c.feed_bytes(f)) == 0
    assert c.integrity["duplicates"] == 1


def test_late_out_of_order_frame_does_not_overwrite_newer_state():
    c = MAVLinkConnector()
    c.feed_bytes(sys_status(remaining=80, seq=10))
    c.feed_bytes(sys_status(remaining=70, seq=11))
    assert c.feed_bytes(sys_status(remaining=99, seq=9)) == []   # late
    assert c.vehicles[1].battery_remaining_pct == 70
    assert c.integrity["late"] == 1


def test_missing_sequence_numbers_counted_as_loss():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=1))
    c.feed_bytes(heartbeat(seq=5))           # 2,3,4 lost
    assert c.integrity["lost"] == 3


def test_sequence_wraparound_is_not_loss_or_late():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=254))
    c.feed_bytes(heartbeat(seq=255))
    assert len(c.feed_bytes(heartbeat(seq=0))) == 1
    assert c.integrity["lost"] == 0 and c.integrity["late"] == 0


def test_reconnect_resets_sequence_tracking():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=200))
    c.disconnect()
    c.connect()
    assert len(c.feed_bytes(heartbeat(seq=3))) == 1  # vehicle rebooted, seq restarted


def test_silent_gap_starts_a_fresh_stream(monkeypatch):
    c = MAVLinkConnector()
    t = [1000.0]
    monkeypatch.setattr(mc.time, "monotonic", lambda: t[0])
    c.feed_bytes(heartbeat(seq=200))
    t[0] += mc._SEQ_STREAM_TIMEOUT_S + 1
    assert len(c.feed_bytes(heartbeat(seq=2))) == 1


def test_two_vehicles_same_message_type_stay_separate():
    c = MAVLinkConnector(asset_mapping_override={1: "DRONE-A", 2: "DRONE-B"})
    e1 = c.feed_bytes(sys_status(remaining=90, sysid=1, seq=1))[0]
    e2 = c.feed_bytes(sys_status(remaining=30, sysid=2, seq=1))[0]   # same seq, different sysid: NOT a duplicate
    assert (e1.source_asset_id, e1.battery.health_percent) == ("DRONE-A", 90)
    assert (e2.source_asset_id, e2.battery.health_percent) == ("DRONE-B", 30)
    assert c.vehicles[1].battery_remaining_pct == 90 and c.vehicles[2].battery_remaining_pct == 30


def test_same_sysid_different_components_do_not_collide_on_sequence():
    c = MAVLinkConnector()
    assert len(c.feed_bytes(heartbeat(seq=7, compid=1))) == 1
    assert c.feed_bytes(heartbeat(seq=7, compid=154)) == []   # gimbal: seq tracked separately, state ignored
    assert c.integrity["duplicates"] == 0
    assert c.integrity["ignored_component"] == 1


def test_gcs_and_non_autopilot_components_never_create_or_update_vehicles():
    c = MAVLinkConnector()
    assert c.feed_bytes(heartbeat(seq=1, sysid=255, compid=190)) == []   # ground station
    assert c.feed_bytes(heartbeat(seq=1, sysid=0)) == []                 # invalid sysid
    assert c.feed_bytes(heartbeat(seq=1, sysid=1, compid=191)) == []     # companion computer
    assert c.vehicles == {}
    assert c.integrity["ignored_sysid"] == 2 and c.integrity["ignored_component"] == 1


def test_unknown_system_id_is_tracked_as_its_own_vehicle_not_merged():
    c = MAVLinkConnector(asset_mapping_override={1: "KNOWN"})
    (e,) = c.feed_bytes(heartbeat(seq=1, sysid=9))
    assert e.source_asset_id == "UAV-MAV-009"       # unmapped => downstream identity resolution decides
    assert 1 not in c.vehicles


def test_unsupported_message_id_is_consumed_not_trusted():
    c = MAVLinkConnector()
    unsupported = struct.pack("<BBBBBBB", 2, 0, 0, 1, 1, 1, 9999 & 0xFF) + bytes([(9999 >> 8) & 0xFF, 0]) + b"\x01\x02" + b"\x00\x00"
    events = c.feed_bytes(bytes([mc.MAVLINK_STX_V2]) + unsupported + heartbeat(seq=2))
    assert len(events) == 1
    assert c.integrity["unsupported_msgid"] == 1


def test_signed_v2_frame_is_framed_correctly_and_following_frame_survives():
    c = MAVLinkConnector()
    events = c.feed_bytes(heartbeat(seq=1, signed=True) + heartbeat(seq=2))
    assert len(events) == 2
    assert c.integrity["signed_frames"] == 1
    assert c.integrity["crc_errors"] == 0


def test_chunked_delivery_across_arbitrary_boundaries():
    c = MAVLinkConnector()
    stream = heartbeat(seq=1) + sys_status(seq=2) + vibration(seq=3)
    events = []
    for i in range(0, len(stream), 3):
        events += c.feed_bytes(stream[i:i + 3])
    assert len(events) == 3


def test_high_frequency_burst_is_all_accepted_in_order_and_linear_time():
    import time as _t

    c = MAVLinkConnector()
    n = 3000
    stream = b"".join(vibration(x=1.0, y=1.0, z=1.0, seq=i) for i in range(n))
    t0 = _t.perf_counter()
    events = c.feed_bytes(stream)
    elapsed = _t.perf_counter() - t0
    assert len(events) == n
    assert c.integrity["lost"] == 0 and c.integrity["duplicates"] == 0
    assert elapsed < 5.0, f"{n} frames took {elapsed:.2f}s"
