"""Rate limiting: a `RateLimiter` interface with a process-local and a shared (Redis) implementation.

Two implementations of one interface (`RateLimiter.check`):

  - `InMemoryRateLimiter`: process-local fixed-window counters. Deterministic, dependency-free; used for tests, local
    development and single-process deployments. With several API workers/instances each process counts on its own,
    so the effective limit is multiplied by the process count.
  - `RedisRateLimiter`: fixed-window counters in a shared Redis (INCR + EXPIRE in one pipeline), so every instance
    sees the same counts. Selected with `RATE_LIMIT_BACKEND=redis` (+ `REDIS_URL`); needs the `redis` package
    (`pip install aerocomply-backend[redis]`). The Redis server itself is deployment infrastructure (external).

Failure policy (enforced by the callers, not by the backends): when the shared store errors, policies listed in
`settings.rate_limit_fail_closed_policies` (and the auth/upload dependency buckets) REJECT the request (503), every
other policy falls back to a local in-memory count so a Redis outage degrades accuracy instead of availability.

Keyed by client IP (the immediate peer, never X-Forwarded-For unless `rate_limit_trust_forwarded_for` is set behind a
proxy you control) plus a bucket name, so the login/refresh/upload limits are independent of each other. Tenant/user
keyed policies live in rate_limit_middleware.py.
"""

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import structlog
from fastapi import Request

from app.core.config import live_settings
from app.core.errors import AeroComplyError
from app.core.metrics import REGISTRY, Counter

log = structlog.get_logger(__name__)

BACKEND_ERRORS = REGISTRY.register(
    Counter("kota_rate_limit_backend_errors_total", "Shared rate-limit store failures, by policy and outcome")
)

_MAX_TRACKED_WINDOWS = 20_000

Decision = tuple[bool, int, int]  # (allowed, retry_after_seconds, remaining)


class RateLimiter(Protocol):
    def check(self, bucket: str, key: str, *, limit: int, window_seconds: int) -> Decision: ...

    def reset(self) -> None: ...


class InMemoryRateLimiter:
    """Process-local fixed-window counter (see module docstring)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, int], int] = {}
        self._clock = clock

    def check(self, bucket: str, key: str, *, limit: int, window_seconds: int) -> Decision:
        now = self._clock()
        window_index = int(now // window_seconds)
        bucket_key = (bucket, key, window_index)
        with self._lock:
            count = self._counts.get(bucket_key, 0) + 1
            self._counts[bucket_key] = count
            if len(self._counts) > _MAX_TRACKED_WINDOWS:
                for k in [k for k in self._counts if k[2] < window_index]:
                    del self._counts[k]
        retry = max(1, int((window_index + 1) * window_seconds - now) + 1)
        return count <= limit, retry, max(0, limit - count)

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


class RedisRateLimiter:
    """Shared fixed-window counter. `client` is any object with redis-py's `pipeline()` (incr/expire/execute)."""

    def __init__(self, client: Any, *, prefix: str = "kota:rl:", clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._prefix = prefix
        self._clock = clock

    def check(self, bucket: str, key: str, *, limit: int, window_seconds: int) -> Decision:
        now = self._clock()
        window_index = int(now // window_seconds)
        redis_key = f"{self._prefix}{bucket}:{key}:{window_index}"
        pipe = self._client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 1)  # a window's key outlives it by 1 s, then disappears
        count = int(pipe.execute()[0])
        retry = max(1, int((window_index + 1) * window_seconds - now) + 1)
        return count <= limit, retry, max(0, limit - count)

    def reset(self) -> None:
        for k in self._client.scan_iter(match=f"{self._prefix}*"):
            self._client.delete(k)


def build_limiter(backend: str, redis_url: str | None = None) -> RateLimiter:
    name = (backend or "memory").strip().lower()
    if name == "memory":
        return InMemoryRateLimiter()
    if name == "redis":
        try:
            import redis  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on the deployment's installed extras
            raise RuntimeError(
                "RATE_LIMIT_BACKEND=redis requires the 'redis' package (pip install aerocomply-backend[redis])"
            ) from exc
        client = redis.Redis.from_url(
            redis_url or live_settings.redis_url, socket_timeout=0.25, socket_connect_timeout=0.25
        )
        return RedisRateLimiter(client)
    raise ValueError(f"unknown rate limit backend {backend!r} (expected 'memory' or 'redis')")


_limiter: RateLimiter | None = None
# Always process-local: used when the shared store fails for a fail-open policy.
_local_fallback = InMemoryRateLimiter()


class RateLimiterUnavailable(Exception):
    def __init__(self, policy: str) -> None:
        super().__init__(f"rate limiter unavailable for policy {policy!r}")
        self.policy = policy


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = build_limiter(live_settings.rate_limit_backend, live_settings.redis_url)
    return _limiter


def set_limiter(limiter: RateLimiter | None) -> None:
    """Install a limiter (tests, or startup wiring). None re-selects from settings on next use."""
    global _limiter
    _limiter = limiter


def fail_closed(policy: str) -> bool:
    return policy in set(live_settings.rate_limit_fail_closed_policies or [])


def check_limit(policy: str, key: str, *, limit: int, window_seconds: int, closed: bool) -> Decision:
    """Count one hit. A failing shared store raises `RateLimiterUnavailable` for fail-closed policies and degrades to a
    process-local count otherwise."""
    try:
        return get_limiter().check(policy, key, limit=limit, window_seconds=window_seconds)
    except Exception as exc:  # noqa: BLE001 - any backend error (connection, timeout, protocol)
        log.error("rate_limit.backend_error", policy=policy, error=type(exc).__name__)
        BACKEND_ERRORS.inc(policy=policy, outcome="rejected" if closed else "local_fallback")
        if closed:
            raise RateLimiterUnavailable(policy) from exc
        return _local_fallback.check(policy, key, limit=limit, window_seconds=window_seconds)


def reset_rate_limits() -> None:
    """Test-only: clear all tracked counters (the limiter is a single process-wide instance)."""
    get_limiter().reset()
    _local_fallback.reset()


def rate_limit(bucket: str, *, limit: int, window_seconds: int) -> Callable[[Request], None]:
    """FastAPI dependency factory. Usage:

    Depends(rate_limit("auth_login", limit=10, window_seconds=60))

    Dependency buckets guard auth and uploads, so a failing shared store rejects (fail closed) instead of letting
    brute force through.
    """

    def _dependency(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        try:
            allowed, _retry, _remaining = check_limit(
                bucket, client_host, limit=limit, window_seconds=window_seconds, closed=True
            )
        except RateLimiterUnavailable:
            raise AeroComplyError(
                "Service temporarily unavailable. Please try again shortly.",
                code="rate_limiter_unavailable",
                status_code=503,
            ) from None
        if not allowed:
            # Deliberately generic and identical regardless of bucket/key, so a rate-limit response never itself
            # becomes an oracle (see M17.2's user-enumeration concern).
            raise AeroComplyError("Too many requests. Please try again shortly.", code="rate_limited", status_code=429)

    return _dependency
