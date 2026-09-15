"""M17.2: minimal application-level rate limiting for the highest-risk
unauthenticated/high-cost endpoints (login, refresh, registration, evidence
upload).

IMPORTANT LIMITATION -- read before relying on this in production:

This is a process-local, in-memory fixed-window counter. It has no shared
backing store (no Redis, no database table) -- deliberately, per this
milestone's explicit instruction not to introduce Redis merely because it
is commonly used, and because this repository has no existing shared-cache
infrastructure to build on. That means:

  - It is effective as long as the backend runs as a SINGLE process/instance
    (e.g. one Render service instance, one uvicorn worker). This matches
    this application's current deployment as documented in this repository
    (no multi-instance/load-balanced configuration exists here).
  - If the backend is ever scaled horizontally to multiple instances or
    multiple worker processes behind a load balancer, each instance/process
    tracks its own counters independently -- an attacker distributing
    requests across instances would see an effective limit multiplied by
    the instance count, not the configured limit. THIS IS A KNOWN GAP, not
    an oversight: a production-grade multi-instance deployment needs an
    external, shared rate limiter (e.g. Redis-backed, or an edge/gateway
    limiter in front of the application) instead of this one. Do not treat
    this module as sufficient once that scaling happens.

Keyed by client IP (from the ASGI connection, i.e. Starlette's
`Request.client.host` -- the immediate peer, not an X-Forwarded-For header,
which is trivially spoofable unless a trusted proxy explicitly strips and
resets it; this repository has no such trusted-proxy configuration to rely
on) plus a caller-supplied bucket name, so the login/refresh/upload limits
are independent of each other.
"""

import threading
import time
from collections.abc import Callable

from fastapi import Request

from app.core.errors import AeroComplyError

# Fixed-window counters: {(bucket, key, window_index): count}. Old windows
# are opportunistically pruned on write so this never grows unbounded even
# though nothing ever runs a background cleanup task (no scheduler exists in
# this codebase -- see app/services/evidence_reconciliation_service.py's own
# docstring on the same point).
_MAX_TRACKED_WINDOWS = 20_000


class _FixedWindowLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, int], int] = {}

    def hit(self, bucket: str, key: str, *, limit: int, window_seconds: int) -> None:
        window_index = int(time.time() // window_seconds)
        bucket_key = (bucket, key, window_index)
        with self._lock:
            count = self._counts.get(bucket_key, 0) + 1
            self._counts[bucket_key] = count
            if len(self._counts) > _MAX_TRACKED_WINDOWS:
                stale = [k for k in self._counts if k[2] < window_index]
                for k in stale:
                    del self._counts[k]

        if count > limit:
            raise AeroComplyError(
                # Deliberately generic and identical regardless of bucket/key,
                # so a rate-limit response never itself becomes an oracle
                # (e.g. distinguishing "this email is close to its own limit"
                # from "this IP is") -- see M17.2's user-enumeration concern.
                "Too many requests. Please try again shortly.",
                code="rate_limited",
                status_code=429,
            )


_limiter = _FixedWindowLimiter()


def reset_rate_limits() -> None:
    """Test-only: clear all tracked counters. The limiter is a single
    process-wide instance (see module docstring), so a long-lived test
    process sharing one fixed TestClient "IP" across hundreds of tests would
    otherwise let one test's login/register/upload calls count against a
    later, unrelated test's budget. Production code never calls this."""
    with _limiter._lock:
        _limiter._counts.clear()


def rate_limit(bucket: str, *, limit: int, window_seconds: int) -> Callable[[Request], None]:
    """FastAPI dependency factory. Usage:

    Depends(rate_limit("auth_login", limit=10, window_seconds=60))
    """

    def _dependency(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        _limiter.hit(bucket, client_host, limit=limit, window_seconds=window_seconds)

    return _dependency
