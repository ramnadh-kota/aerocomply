"""Observability: metrics exposition, what they record, and what they must NOT contain."""
from __future__ import annotations

import re
import uuid

import pytest

from app.core import metrics
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org, _source
from tests.unit.test_m20_mavlink_integrity import heartbeat, vibration


# ------------------------------------------------------------------ unit: the registry itself
def test_counter_gauge_histogram_render_valid_prometheus_text():
    reg = metrics.Registry()
    c = reg.register(metrics.Counter("t_requests_total", "requests"))
    g = reg.register(metrics.Gauge("t_sources", "sources"))
    h = reg.register(metrics.Histogram("t_latency_seconds", "latency", buckets=(0.1, 1.0)))
    c.inc(route="/a", status="200"); c.inc(2, route="/a", status="200"); c.inc(route="/b", status="500")
    g.set(3, health="HEALTHY")
    for v in (0.05, 0.5, 5.0):
        h.observe(v, route="/a")
    text = reg.render()
    assert '# TYPE t_requests_total counter' in text and '# HELP t_requests_total requests' in text
    assert 't_requests_total{route="/a",status="200"} 3' in text
    assert 't_sources{health="HEALTHY"} 3' in text
    assert 't_latency_seconds_bucket{route="/a",le="0.1"} 1' in text
    assert 't_latency_seconds_bucket{route="/a",le="1"} 2' in text          # cumulative
    assert 't_latency_seconds_bucket{route="/a",le="+Inf"} 3' in text
    assert 't_latency_seconds_count{route="/a"} 3' in text
    assert re.search(r't_latency_seconds_sum\{route="/a"\} 5\.55', text)


def test_counters_cannot_decrease_and_label_values_are_escaped():
    c = metrics.Counter("t_x_total", "x")
    with pytest.raises(ValueError):
        c.inc(-1)
    c.inc(route='a"b\\c')
    assert 'route="a\\"b\\\\c"' in "\n".join(c.render())


# ------------------------------------------------------------------ integration
def _platform_headers(client, db_session):
    from tests.integration.conftest import make_platform_admin_headers

    return make_platform_admin_headers(client, db_session)


def test_metrics_endpoint_is_platform_only(client, db_session):
    org_id, h = _org(client, db_session)
    assert client.get("/api/v1/platform/metrics", headers=h).status_code == 403     # tenant admin
    assert client.get("/api/v1/platform/metrics").status_code == 401
    r = client.get("/api/v1/platform/metrics", headers=_platform_headers(client, db_session))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert "kota_http_requests_total" in r.text


def test_http_metrics_use_route_templates_and_never_ids(client, db_session):
    org_id, h = _org(client, db_session, "obs")
    asset = _drone(client, h, reg="OBS-1")
    client.get(f"/api/v1/telemetry/assets/{asset}/latest", headers=h)
    client.get(f"/api/v1/telemetry/assets/{uuid.uuid4()}/latest", headers=h)         # 404 path
    client.get("/api/v1/tenant/billing/invoices")                                       # 401
    text = client.get("/api/v1/platform/metrics", headers=_platform_headers(client, db_session)).text

    assert 'route="/api/v1/telemetry/assets/{asset_id}/latest"' in text
    assert asset not in text and str(org_id) not in text                                # no identifiers anywhere
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text), \
        "a UUID leaked into the metrics output"
    # No identifier as a LABEL (route templates such as /tenant/invitations/{user_id}/cancel are fine:
    # they are templates, not values).
    assert not re.search(r'(user_id|organization_id|asset_id|data_source_id|email)="', text)
    assert re.search(r'kota_http_requests_total\{method="GET",route="/api/v1/telemetry/assets/\{asset_id\}/latest",status="404"\} [1-9]', text)
    assert "kota_auth_failures_total" in text


def test_ingest_metrics_count_outcomes_and_loss_by_connector(client, db_session):
    org_id, h = _org(client, db_session, "obs2")
    asset = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    before = metrics.INGEST_EVENTS.value(connector="MAVLINK", outcome="accepted")
    lost_before = metrics.INGEST_PACKETS_LOST.value(connector="MAVLINK")
    dup_before = metrics.INGEST_EVENTS.value(connector="MAVLINK", outcome="duplicates")
    stream = heartbeat(seq=1) + vibration(1, 1, 1, seq=2) + vibration(1, 1, 1, seq=2) + vibration(1, 1, 1, seq=6)
    rep = _ingest(client, h, sid, stream).json()
    assert rep["accepted"] == 3 and rep["duplicates"] == 1 and rep["packets_lost"] == 3
    assert metrics.INGEST_EVENTS.value(connector="MAVLINK", outcome="accepted") == before + 3
    assert metrics.INGEST_EVENTS.value(connector="MAVLINK", outcome="duplicates") == dup_before + 1
    assert metrics.INGEST_PACKETS_LOST.value(connector="MAVLINK") == lost_before + 3
    assert metrics.INGEST_LATENCY.count(connector="MAVLINK") >= 1


def test_source_health_gauge_reflects_evidence(client, db_session):
    org_id, h = _org(client, db_session, "obs3")
    _source(client, h, "CSV_BATCH", active=False)                       # DRAFT -> INACTIVE
    healthy = _source(client, h, "CSV_BATCH")                           # ACTIVE, no evidence yet -> HEALTHY
    text = client.get("/api/v1/platform/metrics", headers=_platform_headers(client, db_session)).text
    inactive = int(re.search(r'kota_data_sources\{health="INACTIVE"\} (\d+)', text).group(1))
    healthy_n = int(re.search(r'kota_data_sources\{health="HEALTHY"\} (\d+)', text).group(1))
    assert inactive >= 1 and healthy_n >= 1


def test_lisa_tool_metrics_record_latency_and_denials(db_session):
    import pytest as _pt

    from app.core.errors import ForbiddenError
    from app.models.organization import Organization
    from app.schemas.auth import CurrentUser
    from app.services.ai import tools

    org = Organization(name=f"lisa-m-{uuid.uuid4().hex[:6]}")
    db_session.add(org); db_session.flush()
    user = CurrentUser(id=uuid.uuid4(), organization_id=org.id, roles=["ORG_ADMIN"], email="m@example.com",
                       full_name="M", email_verified=True)
    n_before = metrics.LISA_TOOL_LATENCY.count(tool="get_asset_hums_health")
    with _pt.raises(ForbiddenError):                     # organization has no subscription
        tools.execute_tool(db_session, user, "get_asset_hums_health", {"asset_id": str(uuid.uuid4())})
    assert metrics.LISA_TOOL_LATENCY.count(tool="get_asset_hums_health") == n_before + 1
    assert metrics.LISA_TOOL_ERRORS.value(tool="get_asset_hums_health", code="SUITE_ENTITLEMENT_REQUIRED") >= 1


def test_ingest_binds_source_context_into_logs_and_unbinds_after(client, db_session):
    import structlog

    org_id, h = _org(client, db_session, "obs4")
    asset = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    with structlog.testing.capture_logs() as logs:
        _ingest(client, h, sid, vibration(1, 1, 1, seq=1))
    assert any(rec.get("event") == "acquisition.ingested" and rec.get("data_source_id") == sid for rec in logs)
    assert "data_source_id" not in structlog.contextvars.get_contextvars()                 # nothing leaks to the next request


# ------------------------------------------------------------------ instrumentation of HUMS, M7, freshness, worker, exporters
def _metric_value(text: str, name: str, **labels: str) -> float:
    want = {f'{k}="{v}"' for k, v in labels.items()}
    total = 0.0
    for line in text.splitlines():
        if line.startswith(name + "{") or line.startswith(name + " "):
            if want <= set(re.findall(r'(\w+="[^"]*")', line)):
                total += float(line.rsplit(" ", 1)[1])
    return total


def test_hums_m7_and_freshness_metrics_move_with_real_processing(client, db_session):
    org_id, h = _org(client, db_session, "obs-hums")
    asset = _drone(client, h, reg="OBS-HUMS-1")
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    admin = _platform_headers(client, db_session)
    before = client.get("/api/v1/platform/metrics", headers=admin).text

    frames = [heartbeat(seq=1)] + [vibration(1.5, 1.6, 1.7, seq=2 + i) for i in range(6)] + [vibration(45.0, 52.0, 48.0, seq=9)]
    assert _ingest(client, h, sid, b"".join(frames)).status_code in (200, 202)
    after = client.get("/api/v1/platform/metrics", headers=admin).text

    assert _metric_value(after, "kota_hums_evaluations_total", outcome="ok") > _metric_value(before, "kota_hums_evaluations_total", outcome="ok")
    assert "kota_hums_evaluation_duration_seconds_count" in after
    assert sum(_metric_value(after, "kota_hums_exceedances_total", severity=s) for s in ("WARNING", "CRITICAL", "HIGH", "MEDIUM", "LOW")) > \
        sum(_metric_value(before, "kota_hums_exceedances_total", severity=s) for s in ("WARNING", "CRITICAL", "HIGH", "MEDIUM", "LOW"))
    assert _metric_value(after, "kota_m7_signals_total", event="created") > _metric_value(before, "kota_m7_signals_total", event="created")
    # telemetry freshness is derived from stored events at scrape time: just ingested -> small, non-negative
    age = _metric_value(after, "kota_telemetry_newest_event_age_seconds")
    assert 0 <= age < 120
    assert "kota_telemetry_stale_sources" in after


def test_m7_transition_is_counted(client, db_session):
    org_id, h = _org(client, db_session, "obs-m7")
    asset = _drone(client, h, reg="OBS-M7-1")
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    frames = [heartbeat(seq=1)] + [vibration(1.5, 1.6, 1.7, seq=2 + i) for i in range(6)] + [vibration(45.0, 52.0, 48.0, seq=9)]
    _ingest(client, h, sid, b"".join(frames))
    signals = client.get(f"/api/v1/intelligence/assets/{asset}/signals", headers=h).json()
    items = signals if isinstance(signals, list) else signals.get("signals", signals.get("items", []))
    assert items, "expected an M7 signal for the excursion"
    before = metrics.REGISTRY.render()
    r = client.post(f"/api/v1/intelligence/signals/{items[0]["id"]}/acknowledge", headers=h)
    assert r.status_code == 200, r.text
    after = metrics.REGISTRY.render()
    assert _metric_value(after, "kota_m7_signals_total", event="acknowledged") == _metric_value(before, "kota_m7_signals_total", event="acknowledged") + 1


def test_worker_loop_errors_are_counted_and_the_worker_survives(db_session):
    import threading

    from app.worker import run_worker

    calls = {"n": 0}
    stop = threading.Event()

    def broken_factory():
        calls["n"] += 1
        if calls["n"] >= 2:
            stop.set()
        raise ConnectionError("database unreachable")

    before = _metric_value(metrics.REGISTRY.render(), "kota_worker_loop_errors_total")
    run_worker(stop, session_factory=broken_factory, poll_interval=0.01)
    assert calls["n"] >= 2                                   # it kept looping after the first failure
    assert _metric_value(metrics.REGISTRY.render(), "kota_worker_loop_errors_total") >= before + 2
    assert _metric_value(metrics.REGISTRY.render(), "kota_worker_last_poll_timestamp_seconds") > 0


def test_standalone_metrics_endpoint_for_worker_and_listener_processes():
    import urllib.error
    import urllib.request

    import app.listeners.common  # noqa: F401 - registers the listener metrics, as in a real listener process
    import app.services.job_service  # noqa: F401 - and the job metrics, as in a worker process

    from app.core.metrics_server import start_metrics_server

    server = start_metrics_server(0, "127.0.0.1")
    try:
        port = server.server_address[1]
        body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
        assert "# TYPE kota_jobs_total counter" in body and "kota_listener_up" in body
        assert urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5).read() == b"ok"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/secrets", timeout=5)
        assert e.value.code == 404
    finally:
        server.shutdown()


def test_metrics_server_is_off_without_a_port(monkeypatch):
    from app.core.metrics_server import start_metrics_server

    monkeypatch.delenv("METRICS_PORT", raising=False)
    assert start_metrics_server() is None
