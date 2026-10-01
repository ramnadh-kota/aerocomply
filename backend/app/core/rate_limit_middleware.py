"""Policy-based rate limiting for the routes the per-route `rate_limit()` dependency does not cover.

Auth endpoints and evidence upload keep their existing dependency limits (app/core/rate_limit.py); this middleware
adds tenant-aware limits for ingestion, webhooks, LISA, expensive analytics and platform-admin APIs, plus a generous
default per tenant. It uses the same limiter backend as the per-route dependency (rate_limit.py), so `reset_rate_limits()` resets both.

| policy    | matches                                   | key  | default       |
|-----------|-------------------------------------------|------|---------------|
| webhook   | POST .../telemetry/dji/webhook, /webhooks/* | ip | 600 / 60 s    |
| ingest    | POST .../ingest                           | org  | 1200 / 60 s   |
| lisa      | POST /lisa/*                              | user | 30 / 60 s     |
| analytics | GET /hums, /intelligence, /proactive, ... | user | 300 / 60 s    |
| admin     | /platform/*                               | user | 300 / 60 s    |
| default   | everything else                           | org  | 3000 / 60 s   |

Configure with settings.rate_limit_overrides, e.g. {"lisa": "10/60", "default": "off"}; master switch
settings.rate_limit_enabled. Backend: in-memory (default) or shared Redis (settings.rate_limit_backend; see rate_limit.py). If the store fails, policies in
settings.rate_limit_fail_closed_policies answer 503, all others fall back to a local count; a bug in this middleware allows the
request (logged + counted); a bucket that says no rejects.
The tenant/user key comes from a signature-verified JWT; anything else is keyed by client IP (never X-Forwarded-For
unless settings.rate_limit_trust_forwarded_for is set behind a proxy that overwrites it).
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.core.config import live_settings
from app.core.metrics import REGISTRY, Counter
from app.core.rate_limit import RateLimiterUnavailable, check_limit, fail_closed

settings = live_settings
log = structlog.get_logger(__name__)

RATE_LIMITED = REGISTRY.register(Counter("kota_rate_limited_total", "Requests rejected with 429, by policy"))
LIMITER_ERRORS = REGISTRY.register(Counter("kota_rate_limiter_errors_total", "Internal limiter errors (request allowed)"))

DEFAULTS: dict[str, tuple[int, int, str]] = {
    "webhook": (600, 60, "ip"),
    "ingest": (1200, 60, "org"),
    "lisa": (30, 60, "user"),
    "analytics": (300, 60, "user"),
    "admin": (300, 60, "user"),
    "default": (3000, 60, "org"),
}
_ANALYTICS = re.compile(r"/(hums|intelligence|proactive|aerospace-intelligence|mro-intelligence|digital-twin)(/|$)")


def classify(method: str, path: str) -> str | None:
    """Policy name for a request, or None when an existing per-route dependency already governs it (auth)."""
    prefix = settings.api_v1_prefix
    p = path.rstrip("/") or "/"
    if not p.startswith(prefix + "/"):
        return None  # /health, docs: not rate limited
    rest = p[len(prefix):]
    if rest.startswith("/auth/"):
        return None
    if rest.endswith("/telemetry/dji/webhook") or rest.startswith("/webhooks/"):
        return "webhook"
    if method == "POST" and rest.endswith("/ingest"):
        return "ingest"
    if method == "POST" and rest.startswith("/lisa/"):
        return "lisa"
    if rest.startswith("/platform/"):
        return "admin"
    if method == "GET" and _ANALYTICS.match(rest):
        return "analytics"
    return "default"


def resolve(name: str) -> tuple[int, int, str] | None:
    limit, window, key = DEFAULTS[name]
    override = (settings.rate_limit_overrides or {}).get(name)
    if override is None:
        return limit, window, key
    if str(override).strip().lower() in {"off", "none", "disabled"}:
        return None
    try:
        lim_s, win_s = str(override).split("/", 1)
        limit, window = int(lim_s), int(win_s)
        if limit <= 0 or window <= 0:
            raise ValueError
    except ValueError:
        log.error("rate_limit.bad_override", policy=name)  # keep the safe default rather than disabling
        limit, window, _ = DEFAULTS[name]
    return limit, window, key


def _identity(headers: dict[bytes, bytes]) -> tuple[str | None, str | None]:
    auth = headers.get(b"authorization", b"").decode("latin-1")
    if not auth.lower().startswith("bearer "):
        return None, None
    try:
        from app.core.security import decode_token

        payload: dict[str, Any] = decode_token(auth[7:].strip())
    except Exception:  # noqa: BLE001 - invalid token: the auth layer rejects it; we just key by IP
        return None, None
    return payload.get("organization_id"), payload.get("sub")


def _ip(scope: dict, headers: dict[bytes, bytes]) -> str:
    if settings.rate_limit_trust_forwarded_for:
        xff = headers.get(b"x-forwarded-for")
        if xff:
            return xff.decode("latin-1").split(",")[0].strip()[:64]
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _send_json(send: Any, status: int, payload: dict, extra_headers: list[tuple[bytes, bytes]]) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), *extra_headers]})
    await send({"type": "http.response.body", "body": json.dumps(payload).encode()})


class RateLimitMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not settings.rate_limit_enabled or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        verdict: tuple[str, int, int] | None = None
        try:
            policy = classify(scope["method"], scope["path"])
            cfg = resolve(policy) if policy else None
            if policy and cfg:
                limit, window, key_kind = cfg
                headers = dict(scope.get("headers") or [])
                org, user = _identity(headers)
                ip = _ip(scope, headers)
                key = {"org": f"org:{org}" if org else f"ip:{ip}",
                       "user": f"user:{user}" if user else f"ip:{ip}",
                       "ip": f"ip:{ip}"}[key_kind]
                allowed, retry, _remaining = check_limit(
                    policy, key, limit=limit, window_seconds=window, closed=fail_closed(policy)
                )
                if not allowed:
                    verdict = (policy, retry, limit)
        except RateLimiterUnavailable:
            LIMITER_ERRORS.inc()
            log.error("rate_limit.fail_closed", policy=policy)
            await _send_json(
                send, 503,
                {"error": {"code": "rate_limiter_unavailable",
                           "message": "Service temporarily unavailable. Please try again shortly."}},
                [(b"retry-after", b"5")],
            )
            return
        except Exception:  # noqa: BLE001 - fail-safe: limiter bugs must not take the API down
            LIMITER_ERRORS.inc()
            log.exception("rate_limit.internal_error")

        if verdict is None:
            await self.app(scope, receive, send)
            return
        policy, retry, limit = verdict
        RATE_LIMITED.inc(policy=policy)
        log.warning("rate_limit.rejected", policy=policy, path=scope["path"])
        await _send_json(
            send, 429,
            {"error": {"code": "rate_limited", "message": "Too many requests. Please try again shortly."}},
            [(b"retry-after", str(retry).encode()), (b"x-ratelimit-limit", str(limit).encode()),
             (b"x-ratelimit-remaining", b"0")],
        )
