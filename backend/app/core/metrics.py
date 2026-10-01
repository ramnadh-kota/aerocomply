"""Provider-neutral in-process metrics (Prometheus text exposition).

Deliberately dependency-free: counters, gauges and fixed-bucket histograms with labels, rendered in
the Prometheus text format so any scraper (Prometheus, Grafana Agent, Datadog OpenMetrics, ...) can
read them, and swapping to a client library later only replaces this module.

Rules:
  * Labels are LOW-CARDINALITY and NON-IDENTIFYING: route templates, connector types, outcome
    names. Organization / user / asset / source ids never become label values (cardinality blow-up
    and a privacy leak); they live in the structured logs, which carry request_id, organization_id,
    user_id, data_source_id, source_event_id.
  * State is per process. With several workers each exposes its own counters and the scraper sums
    them (standard for Prometheus multi-instance deployments).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

_LOCK = threading.Lock()

DEFAULT_LATENCY_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _key(labels: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in (labels or {}).items()))


def _fmt_labels(key: tuple[tuple[str, str], ...], extra: Sequence[tuple[str, str]] = ()) -> str:
    pairs = [*key, *extra]
    if not pairs:
        return ""
    body = ",".join(f'{k}="{str(v).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"' for k, v in pairs)
    return "{" + body + "}"


class _Metric:
    kind = "untyped"

    def __init__(self, name: str, help_text: str) -> None:
        self.name, self.help = name, help_text

    def _header(self) -> list[str]:
        return [f"# HELP {self.name} {self.help}", f"# TYPE {self.name} {self.kind}"]


class Counter(_Metric):
    kind = "counter"

    def __init__(self, name: str, help_text: str) -> None:
        super().__init__(name, help_text)
        self._values: dict[tuple[tuple[str, str], ...], float] = {}

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        if amount < 0:
            raise ValueError("counters only go up")
        k = _key(labels)
        with _LOCK:
            self._values[k] = self._values.get(k, 0.0) + amount

    def value(self, **labels: str) -> float:
        return self._values.get(_key(labels), 0.0)

    def render(self) -> list[str]:
        with _LOCK:
            items = sorted(self._values.items())
        return self._header() + [f"{self.name}{_fmt_labels(k)} {v:g}" for k, v in items]


class Gauge(_Metric):
    kind = "gauge"

    def __init__(self, name: str, help_text: str) -> None:
        super().__init__(name, help_text)
        self._values: dict[tuple[tuple[str, str], ...], float] = {}

    def set(self, value: float, **labels: str) -> None:
        with _LOCK:
            self._values[_key(labels)] = float(value)

    def reset(self) -> None:
        with _LOCK:
            self._values.clear()

    def render(self) -> list[str]:
        with _LOCK:
            items = sorted(self._values.items())
        return self._header() + [f"{self.name}{_fmt_labels(k)} {v:g}" for k, v in items]


class Histogram(_Metric):
    kind = "histogram"

    def __init__(self, name: str, help_text: str, buckets: Iterable[float] = DEFAULT_LATENCY_BUCKETS) -> None:
        super().__init__(name, help_text)
        self.buckets = tuple(sorted(buckets))
        self._data: dict[tuple[tuple[str, str], ...], dict[str, Any]] = {}

    def observe(self, value: float, **labels: str) -> None:
        k = _key(labels)
        with _LOCK:
            d = self._data.setdefault(k, {"counts": [0] * len(self.buckets), "sum": 0.0, "count": 0})
            for i, upper in enumerate(self.buckets):
                if value <= upper:
                    d["counts"][i] += 1
            d["sum"] += value
            d["count"] += 1

    def count(self, **labels: str) -> int:
        return self._data.get(_key(labels), {"count": 0})["count"]

    def render(self) -> list[str]:
        out = self._header()
        with _LOCK:
            items = sorted((k, dict(v, counts=list(v["counts"]))) for k, v in self._data.items())
        for k, d in items:
            for upper, c in zip(self.buckets, d["counts"], strict=True):
                out.append(f"{self.name}_bucket{_fmt_labels(k, [('le', f'{upper:g}')])} {c}")
            out.append(f"{self.name}_bucket{_fmt_labels(k, [('le', '+Inf')])} {d['count']}")
            out.append(f"{self.name}_sum{_fmt_labels(k)} {d['sum']:g}")
            out.append(f"{self.name}_count{_fmt_labels(k)} {d['count']}")
        return out


class Registry:
    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}

    def register(self, metric: _Metric) -> Any:
        if metric.name in self._metrics:
            return self._metrics[metric.name]
        self._metrics[metric.name] = metric
        return metric

    def render(self) -> str:
        lines: list[str] = []
        for name in sorted(self._metrics):
            lines.extend(self._metrics[name].render())
        return "\n".join(lines) + "\n"


REGISTRY = Registry()

HTTP_REQUESTS = REGISTRY.register(Counter("kota_http_requests_total", "HTTP requests by method, route template and status"))
HTTP_LATENCY = REGISTRY.register(Histogram("kota_http_request_duration_seconds", "HTTP request latency by method and route template"))
AUTH_FAILURES = REGISTRY.register(Counter("kota_auth_failures_total", "Requests rejected as unauthenticated (401)"))
AUTHZ_FAILURES = REGISTRY.register(Counter("kota_authorization_failures_total", "Requests rejected as forbidden (403)"))
INGEST_REQUESTS = REGISTRY.register(Counter("kota_ingest_requests_total", "Ingest calls by connector type"))
INGEST_EVENTS = REGISTRY.register(Counter("kota_ingest_events_total", "Ingested events by connector type and outcome"))
INGEST_PACKETS_LOST = REGISTRY.register(Counter("kota_ingest_packets_lost_total", "Link packets lost, by connector type"))
INGEST_LATENCY = REGISTRY.register(Histogram("kota_ingest_duration_seconds", "Server-side duration of an ingest call, by connector type"))
INGEST_EVENT_AGE = REGISTRY.register(Histogram(
    "kota_ingest_event_age_seconds", "Age of accepted events on arrival (freshness), by connector type",
    buckets=(0.1, 0.5, 1, 5, 15, 60, 300, 900, 3600, 86400)))
LISA_TOOL_LATENCY = REGISTRY.register(Histogram("kota_lisa_tool_duration_seconds", "LISA tool execution latency by tool"))
LISA_TOOL_ERRORS = REGISTRY.register(Counter("kota_lisa_tool_errors_total", "LISA tool failures by tool and error code"))
SOURCES_BY_HEALTH = REGISTRY.register(Gauge("kota_data_sources", "Data sources by evidence-derived health (refreshed on scrape)"))
TELEMETRY_NEWEST_EVENT_AGE = REGISTRY.register(Gauge(
    "kota_telemetry_newest_event_age_seconds", "Seconds since the newest stored telemetry event, deployment-wide (refreshed on scrape)"))
TELEMETRY_STALE_SOURCES = REGISTRY.register(Gauge(
    "kota_telemetry_stale_sources", "Active data sources with no accepted event inside their freshness window (refreshed on scrape)"))
HUMS_EVALUATIONS = REGISTRY.register(Counter("kota_hums_evaluations_total", "HUMS per-sensor evaluations by outcome (ok/failed)"))
HUMS_EVAL_LATENCY = REGISTRY.register(Histogram("kota_hums_evaluation_duration_seconds", "Duration of one HUMS sensor evaluation"))
HUMS_EXCEEDANCES = REGISTRY.register(Counter("kota_hums_exceedances_total", "HUMS exceedances recorded, by severity"))
M7_SIGNALS = REGISTRY.register(Counter("kota_m7_signals_total", "M7 proactive signals by event (created, or the status transitioned to) and type"))
WORKER_LOOP_ERRORS = REGISTRY.register(Counter("kota_worker_loop_errors_total", "Unexpected errors in the worker loop (the loop continues)"))
WORKER_LAST_POLL = REGISTRY.register(Gauge("kota_worker_last_poll_timestamp_seconds", "Unix time of the worker's last queue poll"))


class Timer:
    """`with Timer() as t: ...; t.seconds`"""

    def __enter__(self) -> Timer:
        self._t0 = time.perf_counter()
        self.seconds = 0.0
        return self

    def __exit__(self, *exc: object) -> None:
        self.seconds = time.perf_counter() - self._t0


def _route_template(scope: dict) -> str:
    """The full request path with every path-PARAMETER segment replaced by its `{name}`, e.g.
    /api/v1/telemetry/assets/{asset_id}/latest. Built from the real path + the router's
    path_params (not from the route object, which in mounted/lazily-included routers knows only
    its unprefixed path). Unrouted requests (404s, scanners) share one label so probing random
    URLs cannot create unbounded series."""
    if scope.get("route") is None:
        return "unmatched"
    params = {str(v): k for k, v in (scope.get("path_params") or {}).items()}
    segments = (scope.get("path") or "").split("/")
    return "/".join("{" + params[seg] + "}" if seg in params else seg for seg in segments) or "/"


class MetricsMiddleware:
    """Pure ASGI middleware: request counts and latency by ROUTE TEMPLATE (never the raw path, so
    ids do not explode cardinality or leak), plus 401/403 counters."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        status = {"code": 500}
        t0 = time.perf_counter()

        async def send_wrapper(message: dict) -> None:
            if message.get("type") == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            template = _route_template(scope)
            method = scope.get("method", "GET")
            HTTP_REQUESTS.inc(method=method, route=template, status=str(status["code"]))
            HTTP_LATENCY.observe(time.perf_counter() - t0, method=method, route=template)
            if status["code"] == 401:
                AUTH_FAILURES.inc(route=template)
            elif status["code"] == 403:
                AUTHZ_FAILURES.inc(route=template)
