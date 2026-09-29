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
