"""C5 prerequisites in the MAVLink connector: GPS_RAW_INT is parsed, and unreported GPS/altitude fields stay null."""
import struct

from app.services.edge.mavlink_connector import MAVLinkConnector
from tests.unit.test_m20_mavlink_integrity import frame_v2


def gps_raw(lat=10.0, lon=77.0, fix=3, sats=11, eph=95, **kw):
    return frame_v2(24, struct.pack("<QiiiHHHHBB", 1, int(lat * 1e7), int(lon * 1e7), 123_000, eph, 150, 0, 0, fix, sats), **kw)


def gpi(lat=10.0, lon=77.0, rel_mm=15_000, **kw):
    return frame_v2(33, struct.pack("<IiiiihhhH", 1, int(lat * 1e7), int(lon * 1e7), 120_000, rel_mm, 0, 0, 0, 0), **kw)


def pos(evt):
    return evt.raw_metadata["live_state"]["position"]


def test_gps_raw_int_is_parsed_into_fix_quality():
    (e,) = MAVLinkConnector().feed_bytes(gps_raw(seq=1))
    p = pos(e)
    assert (p["gps_fix_type"], p["gps_fix"], p["satellites"], p["hdop"]) == (3, "3D", 11, 0.95)
    assert p["lat"] == 10.0 and p["lon"] == 77.0 and p["alt_msl_m"] == 123.0
    assert p["alt_rel_m"] is None  # GPS_RAW_INT carries no home-relative altitude


def test_fix_is_unknown_not_zero_before_gps_raw_int_arrives():
    (e,) = MAVLinkConnector().feed_bytes(gpi(seq=1))
    p = pos(e)
    assert p["gps_fix_type"] is None and p["satellites"] is None and p["hdop"] is None
    assert p["alt_rel_m"] == 15.0 and p["alt_msl_m"] == 120.0


def test_no_fix_does_not_publish_a_placeholder_position():
    c = MAVLinkConnector()
    (e,) = c.feed_bytes(gps_raw(lat=0.0, lon=0.0, fix=1, sats=0, seq=1))
    p = pos(e)
    assert p["gps_fix_type"] == 1 and p["lat"] is None and p["lon"] is None
    c.feed_bytes(gps_raw(seq=2))
    (e,) = c.feed_bytes(gps_raw(lat=0.0, lon=0.0, fix=0, sats=0, seq=3))
    assert pos(e)["lat"] == 10.0 and pos(e)["gps_fix_type"] == 0   # last good position kept; the bad fix is visible


def test_unknown_hdop_and_satellites_sentinels():
    (e,) = MAVLinkConnector().feed_bytes(gps_raw(eph=65535, sats=255, seq=1))
    assert pos(e)["hdop"] is None and pos(e)["satellites"] is None
