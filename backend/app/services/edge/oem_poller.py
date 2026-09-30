"""OEM pull-polling for OEM_API data sources.

connection_config:
  {"poll": {"url": "https://api.oem.example/v1/telemetry", "interval_seconds": 60, "cursor_param": "since",
            "auth": "bearer" | "header:X-Api-Key" | "none", "format": "json" | "csv", "max_bytes": 5242880}}
+ secret_reference -> the API credential (never stored in the data source row).

The response body is handed UNCHANGED (JSON wrapped as {"events": [...]}, a bare list, or CSV) to the same batch
connectors the upload endpoint uses, so validation / normalization / dedup / quarantine are identical. The next cursor is
taken from the JSON field "next_cursor" or the X-Next-Cursor header and stored in DataSource.metadata_json["poll_cursor"].

SSRF defence (the URL is tenant-supplied, so this is a security boundary):
  * https only (plain http only to a host explicitly allow-listed by the DEPLOYMENT, never by the tenant)
  * no userinfo in the URL, no redirects followed
  * every resolved address must be public: loopback, private, link-local (incl. cloud metadata 169.254.169.254),
    multicast, reserved, unspecified and IPv4-mapped forms of those are refused
  * hosts inside a private network can be allowed only through settings.oem_allowed_private_hosts (operator config)
  * response size is capped while streaming; timeouts are short
Known residual risk: DNS is validated then resolved again by the HTTP client (rebinding window). Run the worker in a
network segment with egress filtering for defence in depth."""
from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core import secrets as secrets_layer
from app.core.config import live_settings

settings = live_settings

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
HARD_MAX_BYTES = 25 * 1024 * 1024
MIN_INTERVAL, MAX_INTERVAL = 15, 86_400
TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)


class PollConfigError(ValueError):
    """Permanent misconfiguration or a blocked target: retrying cannot help."""


class PollTransientError(RuntimeError):
    """Network / 5xx / rate limit: worth retrying with backoff."""


@dataclass
class PollConfig:
    url: str
    interval_seconds: int
    cursor_param: str | None
    auth: str
    fmt: str
    max_bytes: int


def parse_config(connection_config: dict[str, Any] | None) -> PollConfig:
    cfg = (connection_config or {}).get("poll")
    if not isinstance(cfg, dict) or not cfg.get("url"):
        raise PollConfigError("connection_config.poll.url is required")
    interval = int(cfg.get("interval_seconds", 60))
    if not MIN_INTERVAL <= interval <= MAX_INTERVAL:
        raise PollConfigError(f"poll.interval_seconds must be between {MIN_INTERVAL} and {MAX_INTERVAL}")
    fmt = str(cfg.get("format", "json")).lower()
    if fmt not in ("json", "csv"):
        raise PollConfigError("poll.format must be json or csv")
    auth = str(cfg.get("auth", "none"))
    if not (auth in ("none", "bearer") or (auth.startswith("header:") and len(auth) > 7)):
        raise PollConfigError("poll.auth must be none, bearer or header:<Name>")
    max_bytes = min(int(cfg.get("max_bytes", DEFAULT_MAX_BYTES)), HARD_MAX_BYTES)
    if max_bytes <= 0:
        raise PollConfigError("poll.max_bytes must be positive")
    cursor_param = cfg.get("cursor_param")
    return PollConfig(url=str(cfg["url"]), interval_seconds=interval, cursor_param=str(cursor_param) if cursor_param else None,
                      auth=auth, fmt=fmt, max_bytes=max_bytes)


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved
                or ip.is_unspecified or (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10")))


def resolve_host(host: str, port: int):
    """DNS resolution seam (patched in tests without touching the process-wide resolver)."""
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def assert_safe_url(url: str) -> None:
    """Raise PollConfigError unless `url` is an acceptable outbound target (see module docstring)."""
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise PollConfigError("credentials in the URL are not allowed")
    host = (parts.hostname or "").strip().lower()
    if not host:
        raise PollConfigError("URL has no host")
    allowed_private = {h.strip().lower() for h in (getattr(settings, "oem_allowed_private_hosts", None) or [])}
    operator_allowed = host in allowed_private
    if parts.scheme != "https" and not (parts.scheme == "http" and operator_allowed):
        raise PollConfigError("only https URLs are allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise PollConfigError("invalid port") from exc
    try:
        infos = resolve_host(host, port or (443 if parts.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise PollTransientError(f"cannot resolve {host}") from exc
    if not infos:
        raise PollTransientError(f"cannot resolve {host}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not _is_public(ip) and not operator_allowed:
            raise PollConfigError("target resolves to a non-public address")


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=False)


# overridable in tests (an httpx.MockTransport client); production always uses _client
client_factory = _client


def poll_once(connection_config: dict[str, Any] | None, secret_reference: str | None, cursor: str | None
              ) -> tuple[bytes, str | None]:
    """One authenticated pull. Returns (payload bytes for the batch connector, next cursor)."""
    cfg = parse_config(connection_config)
    assert_safe_url(cfg.url)
    headers = {"Accept": "text/csv" if cfg.fmt == "csv" else "application/json", "User-Agent": "kota-poller/1"}
    if cfg.auth != "none":
        secret = secrets_layer.resolve(secret_reference)
        if not secret:
            raise PollConfigError("the poll credential (secret_reference) is not available")
        if cfg.auth == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        else:
            headers[cfg.auth.split(":", 1)[1]] = secret
    params = {cfg.cursor_param: cursor} if (cfg.cursor_param and cursor) else None
    body = bytearray()
    try:
        with client_factory() as client, client.stream("GET", cfg.url, headers=headers, params=params) as resp:
            if 300 <= resp.status_code < 400:
                raise PollConfigError("redirects are not followed")
            if resp.status_code in (401, 403):
                raise PollConfigError(f"OEM API refused the credential (HTTP {resp.status_code})")
            if resp.status_code == 429 or resp.status_code >= 500:
                raise PollTransientError(f"OEM API HTTP {resp.status_code}")
            if resp.status_code != 200:
                raise PollConfigError(f"unexpected OEM API status {resp.status_code}")
            ctype = resp.headers.get("content-type", "").lower()
            if cfg.fmt == "json" and "json" not in ctype:
                raise PollConfigError("OEM API did not return JSON")
            header_cursor = resp.headers.get("x-next-cursor")
            for chunk in resp.iter_bytes():
                body.extend(chunk)
                if len(body) > cfg.max_bytes:
                    raise PollConfigError("OEM API response exceeds the size limit")
    except httpx.HTTPError as exc:
        raise PollTransientError(f"{type(exc).__name__} talking to the OEM API") from exc

    next_cursor = header_cursor
    if cfg.fmt == "json":
        try:
            doc = json.loads(bytes(body))
        except ValueError as exc:
            raise PollConfigError("OEM API returned invalid JSON") from exc
        if isinstance(doc, dict) and doc.get("next_cursor") is not None:
            next_cursor = str(doc["next_cursor"])[:256]
    return bytes(body), (next_cursor[:256] if next_cursor else None)


_WRAPPER_KEYS = ("events", "data", "records", "items", "telemetry", "readings")


def is_empty_payload(raw: bytes, fmt: str) -> bool:
    """True when the OEM returned no new records (an empty poll is healthy, not a failure)."""
    if fmt == "csv":
        return len([ln for ln in raw.decode("utf-8", "replace").splitlines() if ln.strip()]) <= 1
    try:
        doc = json.loads(raw)
    except ValueError:
        return False
    if isinstance(doc, list):
        return len(doc) == 0
    if isinstance(doc, dict):
        for key in _WRAPPER_KEYS:
            if isinstance(doc.get(key), list):
                return len(doc[key]) == 0
    return False
