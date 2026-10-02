"""C4: SSE broker cursor/replay contract and time-based freshness (no database)."""
import uuid
from datetime import UTC, datetime, timedelta

from app.schemas.live_state import compute_freshness
from app.services.live_state_service import LiveBroker


def test_freshness_is_time_based():
    now = datetime.now(UTC)
    assert compute_freshness(None, now).state == "NO_DATA"
    assert compute_freshness(now - timedelta(seconds=3), now).state == "FRESH"
    assert compute_freshness(now - timedelta(seconds=30), now).state == "STALE"
    assert compute_freshness(now - timedelta(seconds=300), now).state == "LOST"


def test_broker_cursor_contract():
    b = LiveBroker()
    org = uuid.uuid4()
    e1 = b.publish(org, "state", {"a": 1})
    e2 = b.publish(org, "state", {"a": 2})
    assert e2["n"] == e1["n"] + 1
    assert [e["n"] for e in b.replay_after(org, e1["id"])] == [e2["n"]]
    assert b.replay_after(org, e2["id"]) == []
    assert b.replay_after(org, "deadbeef:1") is None         # other epoch (restart / other worker)
    assert b.replay_after(org, f"{b.epoch}:999") is None      # ahead of the server
    assert b.replay_after(org, "garbage") is None


def test_replay_window_eviction_forces_resync():
    b = LiveBroker(window=3)
    org = uuid.uuid4()
    ids = [b.publish(org, "state", {"i": i})["id"] for i in range(6)]
    assert b.replay_after(org, ids[0]) is None                # part of the gap was evicted
    assert len(b.replay_after(org, ids[3])) == 2


def test_tenants_have_independent_sequences():
    b = LiveBroker()
    o1, o2 = uuid.uuid4(), uuid.uuid4()
    b.publish(o1, "state", {})
    b.publish(o1, "state", {})
    assert b.publish(o2, "state", {})["n"] == 1
