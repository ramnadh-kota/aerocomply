"""C3: MISSION_CURRENT / MISSION_ITEM_REACHED / STATUSTEXT parsing and the live_state event contract."""
from __future__ import annotations

import struct

from app.services.edge.mavlink_connector import MAVLinkConnector, sanitize_statustext
from tests.unit.test_m20_mavlink_integrity import frame_v2, heartbeat, sys_status


def mission_current(item=3, total=8, state=3, **kw):
    return frame_v2(42, struct.pack("<HHBB", item, total, state, 0), **kw)


def reached(item=2, **kw):
    return frame_v2(46, struct.pack("<H", item), **kw)


def statustext(text: bytes, sev=4, cid=0, chunk=0, **kw):
    return frame_v2(253, struct.pack("<B50sHB", sev, text, cid, chunk), **kw)


def ls(evt):
    return evt.raw_metadata["live_state"]


def test_mission_current_and_reached():
    c = MAVLinkConnector()
    (e,) = c.feed_bytes(mission_current(seq=1))
    m = ls(e)["mission"]
    assert (m["current_seq"], m["total_items"], m["state"]) == (3, 8, "ACTIVE")
    (e,) = c.feed_bytes(reached(item=2, seq=2))
    m = ls(e)["mission"]
    assert m["last_reached_seq"] == 2 and m["last_reached_at"] and m["current_seq"] == 3
    assert ls(e)["trigger"]["message_type"] == "MISSION_ITEM_REACHED"


def test_total_zero_is_unknown_and_unreported_groups_are_null():
    c = MAVLinkConnector()
    (e,) = c.feed_bytes(mission_current(total=0, state=0, seq=1))
    s = ls(e)
    assert s["mission"]["total_items"] is None
    assert s["position"]["lat"] is None and s["battery"]["voltage_v"] is None
    assert s["position"]["observed_at"] is None and s["mode"]["armed"] is None
    assert s["schema"] == "kota.drone.live_state.v1"


def test_statustext_simple_sanitized_and_bounded():
    c = MAVLinkConnector()
    (e,) = c.feed_bytes(statustext(b"PreArm: Compass\x07 variance\x00junk", seq=1))
    t = ls(e)["status_texts"][0]
    assert t["text"] == "PreArm: Compass variance" and t["severity_name"] == "WARNING" and t["untrusted"] is True
    for i in range(15):
        (e,) = c.feed_bytes(statustext(b"msg %d" % i, seq=2 + i))
    texts = ls(e)["status_texts"]
    assert len(texts) == 10 and texts[0]["text"] == "msg 14"


def test_statustext_chunks_reassembled():
    c = MAVLinkConnector()
    c.feed_bytes(statustext(b"A" * 50, cid=7, chunk=0, seq=1))
    (e,) = c.feed_bytes(statustext(b"tail", cid=7, chunk=1, seq=2))
    assert ls(e)["status_texts"][0]["text"] == "A" * 50 + "tail"


def test_cumulative_snapshot_and_trigger_metadata():
    c = MAVLinkConnector()
    c.feed_bytes(heartbeat(seq=1))
    (e,) = c.feed_bytes(sys_status(seq=2))
    s = ls(e)
    assert s["mode"]["armed"] is True and s["battery"]["remaining_pct"] == 87
    assert s["trigger"]["component_id"] == 1 and s["trigger"]["link_seq"] == 2 and s["trigger"]["signed"] is False


def test_sanitize():
    assert sanitize_statustext("a\x00b") == "ab"
    assert len(sanitize_statustext("x" * 500)) == 200
