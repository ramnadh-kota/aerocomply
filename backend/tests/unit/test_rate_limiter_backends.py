"""RateLimiter backends: deterministic clock, a fake shared store standing in for Redis, tenant/user keys and failure policy."""
import asyncio

import pytest

from app.core import rate_limit as rl
from app.core import rate_limit_middleware as rlm
from app.core.config import live_settings


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeRedis:
    """Just enough of redis-py: a shared dict with pipeline(incr, expire) + scan_iter/delete. One instance == one server."""

    def __init__(self):
        self.data: dict[str, int] = {}
        self.ttl: dict[str, int] = {}

    def pipeline(self):
        store = self

        class Pipe:
            def __init__(self):
                self.ops = []

            def incr(self, k):
                self.ops.append(("incr", k))

            def expire(self, k, s):
                self.ops.append(("expire", k, s))

            def execute(self):
                out = []
                for op in self.ops:
                    if op[0] == "incr":
                        store.data[op[1]] = store.data.get(op[1], 0) + 1
                        out.append(store.data[op[1]])
                    else:
                        store.ttl[op[1]] = op[2]
                        out.append(True)
                return out

        return Pipe()

    def scan_iter(self, match):
        prefix = match.rstrip("*")
        return [k for k in list(self.data) if k.startswith(prefix)]

    def delete(self, k):
        self.data.pop(k, None)


class DownRedis:
    def pipeline(self):
        raise ConnectionError("redis down")


def test_in_memory_window_and_reset():
    clock = Clock()
    lim = rl.InMemoryRateLimiter(clock)
    assert [lim.check("b", "k", limit=2, window_seconds=60)[0] for _ in range(3)] == [True, True, False]
    clock.t += 60  # next window: counters start again
    assert lim.check("b", "k", limit=2, window_seconds=60)[0] is True
    lim.reset()
    assert lim.check("b", "k", limit=1, window_seconds=60) == (True, lim.check("b", "zz", limit=1, window_seconds=60)[1], 0)


def test_buckets_and_keys_are_independent():
    lim = rl.InMemoryRateLimiter(Clock())
    assert lim.check("login", "org:a", limit=1, window_seconds=60)[0]
    assert not lim.check("login", "org:a", limit=1, window_seconds=60)[0]
    assert lim.check("login", "org:b", limit=1, window_seconds=60)[0]      # other tenant unaffected
    assert lim.check("ingest", "org:a", limit=1, window_seconds=60)[0]     # other policy unaffected


def test_two_instances_sharing_redis_share_one_budget():
    server, clock = FakeRedis(), Clock()
    a, b = rl.RedisRateLimiter(server, clock=clock), rl.RedisRateLimiter(server, clock=clock)
    results = [a.check("p", "org:1", limit=3, window_seconds=60)[0], b.check("p", "org:1", limit=3, window_seconds=60)[0],
               a.check("p", "org:1", limit=3, window_seconds=60)[0], b.check("p", "org:1", limit=3, window_seconds=60)[0]]
    assert results == [True, True, True, False]      # process-local limiters would have allowed 6
    assert all(ttl == 61 for ttl in server.ttl.values())
    assert all(k.startswith("kota:rl:p:org:1:") for k in server.data)
    a.reset()
    assert server.data == {}


def test_build_limiter_selection():
    assert isinstance(rl.build_limiter("memory"), rl.InMemoryRateLimiter)
    with pytest.raises(ValueError):
        rl.build_limiter("carrier-pigeon")


@pytest.fixture
def down_limiter():
    rl.set_limiter(rl.RedisRateLimiter(DownRedis()))
    yield
    rl.set_limiter(None)
    rl._local_fallback.reset()


def test_backend_down_fail_closed_policy_rejects(down_limiter):
    with pytest.raises(rl.RateLimiterUnavailable):
        rl.check_limit("webhook", "ip:1", limit=5, window_seconds=60, closed=rl.fail_closed("webhook"))
    assert rl.fail_closed("webhook") and rl.fail_closed("admin") and not rl.fail_closed("default")


def test_backend_down_fail_open_policy_degrades_to_local_count(down_limiter):
    decisions = [rl.check_limit("default", "org:1", limit=2, window_seconds=60, closed=False)[0] for _ in range(3)]
    assert decisions == [True, True, False]   # still limited, just per-process


def test_dependency_buckets_fail_closed_with_503(down_limiter):
    class Req:
        client = type("C", (), {"host": "9.9.9.9"})()

    from app.core.errors import AeroComplyError

    with pytest.raises(AeroComplyError) as e:
        rl.rate_limit("auth_login", limit=5, window_seconds=60)(Req())
    assert e.value.status_code == 503


def test_middleware_returns_503_for_fail_closed_policy(down_limiter):
    sent = []

    async def app(scope, receive, send):  # must not be reached
        raise AssertionError("request should have been rejected")

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": "GET", "path": "/api/v1/platform/organizations", "headers": [], "client": ("1.2.3.4", 1)}
    assert live_settings.rate_limit_enabled
    asyncio.run(rlm.RateLimitMiddleware(app)(scope, None, send))
    assert sent[0]["status"] == 503
