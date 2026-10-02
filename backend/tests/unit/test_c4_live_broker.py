"""C4: broker cursor / replay semantics (no database)."""
import asyncio
import uuid

from app.services.live_state_service import LiveBroker

ORG, OTHER = uuid.uuid4(), uuid.uuid4()


def test_replay_after_cursor_is_tenant_scoped_and_ordered():
    b = LiveBroker()
    first = b.publish(ORG, "state", {"i": 1})
    b.publish(OTHER, "state", {"i": 99})
    b.publish(ORG, "state", {"i": 2})
    b.publish(ORG, "state", {"i": 3})
    got = b.replay_after(ORG, first["id"])
    assert [e["data"]["i"] for e in got] == [2, 3]
    assert b.replay_after(ORG, b.cursor(ORG)) == []
    assert b.replay_after(OTHER, f"{b.epoch}:0")[0]["data"]["i"] == 99


def test_unusable_cursors_force_resync():
    b = LiveBroker(window=3)
    for i in range(10):
        b.publish(ORG, "state", {"i": i})
    assert b.replay_after(ORG, "other-epoch:3") is None      # restart / another worker
    assert b.replay_after(ORG, f"{b.epoch}:999") is None      # from the future
    assert b.replay_after(ORG, "garbage") is None and b.replay_after(ORG, None) is None
    assert b.replay_after(ORG, f"{b.epoch}:2") is None        # evicted from the window
    assert [e["data"]["i"] for e in b.replay_after(ORG, f"{b.epoch}:8")] == [8, 9]


def test_subscriber_receives_and_overflow_is_flagged():
    async def run():
        b = LiveBroker()
        sub = b.subscribe(ORG)
        b.publish(OTHER, "state", {})
        b.publish(ORG, "state", {"x": 1})
        item = await asyncio.wait_for(sub.queue.get(), 1)
        assert item["data"] == {"x": 1} and sub.queue.empty()
        for _ in range(300):
            b.publish(ORG, "state", {})
        await asyncio.sleep(0.05)
        assert sub.overflowed
        b.unsubscribe(sub)

    asyncio.run(run())
