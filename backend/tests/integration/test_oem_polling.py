"""OEM pull polling: SSRF guard, request construction, cursoring, empty polls, failure classes, scheduling, tenancy.
HTTP is simulated with httpx.MockTransport; DNS with a patched resolver. Nothing here talks to a real OEM API."""
from __future__ import annotations

import json
import socket
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select

from app import scheduler
from app.core import secrets
from app.models.background_job import BackgroundJob, JobStatus
from app.models.data_source import DataSource
from app.models.hums import HUMSSensorReading
from app.services import job_handlers, job_service
from app.services.edge import oem_poller as op
from tests.integration.test_acquisition_pipeline import _drone, _org, _source

PUBLIC_IP = "93.184.216.34"
URL = "https://api.oem.example/v1/telemetry"


@pytest.fixture(autouse=True)
def dns(monkeypatch):
    table = {"api.oem.example": PUBLIC_IP, "localhost": "127.0.0.1", "internal.corp": "10.1.2.3", "rebind.evil": "127.0.0.1",
             "meta.evil": "169.254.169.254", "v6.evil": "::1", "mapped.evil": "::ffff:127.0.0.1"}

    def fake(host, port):
        ip = table.get(host, host)
        fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(fam, socket.SOCK_STREAM, 6, "", (ip, port) + ((0, 0) if fam == socket.AF_INET6 else ()))]

    monkeypatch.setattr(op, "resolve_host", fake)


def mock_client(handler):
    op.client_factory = lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=op.TIMEOUT)


@pytest.fixture(autouse=True)
def restore_factory():
    yield
    op.client_factory = op._client


def cfg(**poll):
    return {"poll": {"url": URL, "interval_seconds": 60, **poll}}


# ------------------------------------------------------------------ SSRF guard
@pytest.mark.parametrize("url", [
    "http://api.oem.example/x",                       # plain http
    "https://127.0.0.1/x", "https://localhost/x", "https://10.0.0.5/x", "https://192.168.1.1/x",
    "https://172.16.0.9/x", "https://169.254.169.254/latest/meta-data", "https://[::1]/x", "https://0.0.0.0/x",
    "https://100.64.0.1/x", "https://internal.corp/x", "https://rebind.evil/x", "https://meta.evil/x",
    "https://v6.evil/x", "https://mapped.evil/x", "https://user:pw@api.oem.example/x", "ftp://api.oem.example/x",
    "file:///etc/passwd", "https:///nohost",
])
def test_ssrf_targets_are_refused(url):
    with pytest.raises(op.PollConfigError):
        op.assert_safe_url(url)


def test_public_https_is_allowed_and_operator_can_allow_a_private_host():
    op.assert_safe_url(URL)
    op.settings.oem_allowed_private_hosts = ["internal.corp"]
    try:
        op.assert_safe_url("https://internal.corp/x")
        op.assert_safe_url("http://internal.corp/x")                 # operator-allowed hosts may use http
        with pytest.raises(op.PollConfigError):
            op.assert_safe_url("https://rebind.evil/x")             # ...but only THOSE hosts
    finally:
        op.settings.oem_allowed_private_hosts = []


def test_config_validation():
    for bad in ({}, {"poll": {}}, cfg(interval_seconds=1), cfg(interval_seconds=10**7), cfg(format="xml"),
                cfg(auth="basic"), cfg(auth="header:"), cfg(max_bytes=0)):
        with pytest.raises(op.PollConfigError):
            op.parse_config(bad)
    ok = op.parse_config(cfg(auth="header:X-Api-Key", max_bytes=10**12))
    assert ok.auth == "header:X-Api-Key" and ok.max_bytes == op.HARD_MAX_BYTES


# ------------------------------------------------------------------ requests
def test_bearer_credential_and_cursor_are_sent_and_next_cursor_is_read(monkeypatch):
    monkeypatch.setenv(secrets.env_name("datasource/oem/key"), "tok-123")
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"], seen["params"], seen["host"] = req.headers.get("authorization"), dict(req.url.params), req.url.host
        return httpx.Response(200, json={"events": [{"a": 1}], "next_cursor": "c2"}, headers={"content-type": "application/json"})

    mock_client(handler)
    raw, nxt = op.poll_once(cfg(auth="bearer", cursor_param="since"), "datasource/oem/key", "c1")
    assert seen == {"auth": "Bearer tok-123", "params": {"since": "c1"}, "host": "api.oem.example"} and nxt == "c2"
    assert json.loads(raw)["events"] == [{"a": 1}]


def test_custom_header_auth_and_missing_credential(monkeypatch):
    mock_client(lambda r: httpx.Response(200, json=[], headers={"x-next-cursor": "h9"}))
    with pytest.raises(op.PollConfigError, match="credential"):
        op.poll_once(cfg(auth="header:X-Api-Key"), "datasource/none/key", None)
    monkeypatch.setenv(secrets.env_name("datasource/hdr/key"), "k")
    got = {}
    mock_client(lambda r: (got.update(h=r.headers.get("x-api-key")), httpx.Response(200, json=[], headers={"x-next-cursor": "h9"}))[1])
    _, nxt = op.poll_once(cfg(auth="header:X-Api-Key"), "datasource/hdr/key", None)
    assert got["h"] == "k" and nxt == "h9"


@pytest.mark.parametrize("status,exc", [(401, op.PollConfigError), (403, op.PollConfigError), (404, op.PollConfigError),
                                        (302, op.PollConfigError), (429, op.PollTransientError),
                                        (500, op.PollTransientError), (503, op.PollTransientError)])
def test_status_classification(status, exc):
    mock_client(lambda r: httpx.Response(status, headers={"location": "https://127.0.0.1/"}))
    with pytest.raises(exc):
        op.poll_once(cfg(), None, None)


def test_network_errors_are_transient_and_bad_bodies_are_permanent():
    def boom(req):
        raise httpx.ConnectTimeout("t")

    mock_client(boom)
    with pytest.raises(op.PollTransientError):
        op.poll_once(cfg(), None, None)
    mock_client(lambda r: httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}))
    with pytest.raises(op.PollConfigError, match="JSON"):
        op.poll_once(cfg(), None, None)
    mock_client(lambda r: httpx.Response(200, content=b"{oops", headers={"content-type": "application/json"}))
    with pytest.raises(op.PollConfigError, match="invalid JSON"):
        op.poll_once(cfg(), None, None)


def test_response_size_is_capped_while_streaming():
    mock_client(lambda r: httpx.Response(200, content=b'{"events":[' + b"1," * 5000 + b'1]}', headers={"content-type": "application/json"}))
    with pytest.raises(op.PollConfigError, match="size"):
        op.poll_once(cfg(max_bytes=1000), None, None)


def test_empty_payload_detection():
    assert op.is_empty_payload(b"[]", "json") and op.is_empty_payload(b'{"events": []}', "json")
    assert not op.is_empty_payload(b'{"events": [{"a":1}]}', "json") and not op.is_empty_payload(b"garbage", "json")
    assert op.is_empty_payload(b"a,b\n", "csv") and not op.is_empty_payload(b"a,b\n1,2\n", "csv")


# ------------------------------------------------------------------ end to end through the queue
def _oem_source(client, h, reg, **poll):
    body = {"name": f"oem-{uuid.uuid4().hex[:6]}", "connector_type": "OEM_API",
            "connection_config": cfg(**poll), "secret_reference": "datasource/e2e/key"}
    r = client.post("/api/v1/data-sources", headers=h, json=body)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": "ACTIVE"}).status_code == 200
    return uuid.UUID(sid)


def _drain(db):
    while job_service.run_one(db, worker_id="w", job_types=[job_handlers.POLL]):
        pass


def test_scheduler_polls_sources_once_per_interval_and_cursor_advances(client, db_session, monkeypatch):
    monkeypatch.setenv(secrets.env_name("datasource/e2e/key"), "k")
    org_id, h = _org(client, db_session, "oem1")
    _drone(client, h, reg="OEM-1")
    sid = _oem_source(client, h, "OEM-1", auth="bearer", cursor_param="since")
    calls = []

    def handler(req: httpx.Request):
        calls.append(dict(req.url.params))
        n = len(calls)
        events = [{"asset_id": "OEM-1", "sensor_code": "TEMP", "value": 20 + n, "unit": "C",
                   "timestamp": f"2026-09-0{n}T10:00:00Z"}] if n <= 2 else []
        return httpx.Response(200, json={"events": events, "next_cursor": f"cur{n}"}, headers={"content-type": "application/json"})

    mock_client(handler)
    t0 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
    assert scheduler.enqueue_polls(db_session, now=t0) >= 1
    assert scheduler.enqueue_polls(db_session, now=t0.replace(second=30)) == 0        # same interval: no second job
    _drain(db_session)
    src = db_session.get(DataSource, sid)
    assert calls[0] == {} and src.metadata_json["poll_cursor"] == "cur1" and src.total_events_ingested == 1

    scheduler.enqueue_polls(db_session, now=t0.replace(minute=5))                      # next interval
    _drain(db_session)
    assert calls[1] == {"since": "cur1"} and src.metadata_json["poll_cursor"] == "cur2" and src.total_events_ingested == 2

    scheduler.enqueue_polls(db_session, now=t0.replace(minute=10))                     # OEM has nothing new
    _drain(db_session)
    db_session.refresh(src)
    assert src.consecutive_failures == 0 and src.last_seen_at is not None and src.total_events_ingested == 2
    n = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org_id))
    assert n == 2


def test_replayed_page_after_a_lost_cursor_is_deduplicated(client, db_session, monkeypatch):
    monkeypatch.setenv(secrets.env_name("datasource/e2e/key"), "k")
    org_id, h = _org(client, db_session, "oem2")
    _drone(client, h, reg="OEM-2")
    sid = _oem_source(client, h, "OEM-2", auth="bearer")
    page = {"events": [{"asset_id": "OEM-2", "sensor_code": "T", "value": 1, "unit": "C", "timestamp": "2026-09-01T10:00:00Z"}]}
    mock_client(lambda r: httpx.Response(200, json=page, headers={"content-type": "application/json"}))
    t0 = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    for minute in (0, 5):
        scheduler.enqueue_polls(db_session, now=t0.replace(minute=minute))
        _drain(db_session)
    src = db_session.get(DataSource, sid)
    assert src.total_events_ingested == 1 and src.total_events_duplicate == 1


def test_blocked_target_dead_letters_immediately_and_is_visible_on_the_source(client, db_session):
    org_id, h = _org(client, db_session, "oem3")
    sid = _oem_source(client, h, "x", url="https://127.0.0.1/steal")
    called = []
    mock_client(lambda r: (called.append(1), httpx.Response(200, json=[]))[1])
    job, _ = job_service.enqueue(db_session, job_type=job_handlers.POLL, organization_id=org_id, data_source_id=sid,
                                 idempotency_key="blocked")
    _drain(db_session)
    db_session.refresh(job)
    src = db_session.get(DataSource, sid)
    assert called == [] and job.status == JobStatus.DEAD and job.attempts == 1
    assert src.last_error.startswith("poll refused:") and src.consecutive_failures == 1


def test_transient_failure_retries_then_recovers(client, db_session, monkeypatch):
    monkeypatch.setenv(secrets.env_name("datasource/e2e/key"), "k")
    org_id, h = _org(client, db_session, "oem4")
    _drone(client, h, reg="OEM-4")
    sid = _oem_source(client, h, "OEM-4", auth="bearer")
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"events": [{"asset_id": "OEM-4", "sensor_code": "T", "value": 1, "unit": "C",
                                                     "timestamp": "2026-09-01T10:00:00Z"}]}, headers={"content-type": "application/json"})

    mock_client(handler)
    job, _ = job_service.enqueue(db_session, job_type=job_handlers.POLL, organization_id=org_id, data_source_id=sid,
                                 idempotency_key="retry")
    job_service.run_one(db_session, worker_id="w", job_types=[job_handlers.POLL])
    db_session.refresh(job)
    assert job.status == JobStatus.QUEUED and "OEM API HTTP 503" in job.last_error
    job.run_after = datetime.now(UTC)
    db_session.flush()
    job_service.run_one(db_session, worker_id="w", job_types=[job_handlers.POLL])
    db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED and db_session.get(DataSource, sid).total_events_ingested == 1


def test_paused_source_is_skipped_and_foreign_source_cannot_be_polled(client, db_session):
    org_a, ha = _org(client, db_session, "oem5a")
    org_b, hb = _org(client, db_session, "oem5b")
    sid = _oem_source(client, ha, "x")
    client.patch(f"/api/v1/data-sources/{sid}", headers=ha, json={"status": "PAUSED"})
    mock_client(lambda r: httpx.Response(500))
    j1, _ = job_service.enqueue(db_session, job_type=job_handlers.POLL, organization_id=org_a, data_source_id=sid, idempotency_key="p")
    # a job that names org B but org A's source must never run against it
    j2, _ = job_service.enqueue(db_session, job_type=job_handlers.POLL, organization_id=org_b, data_source_id=sid, idempotency_key="x")
    _drain(db_session)
    db_session.refresh(j1)
    db_session.refresh(j2)
    assert j1.status == JobStatus.SUCCEEDED and j1.result == {"skipped": "source is not an ACTIVE OEM_API source"}
    assert j2.status == JobStatus.DEAD and "not found" in j2.last_error
    assert scheduler.enqueue_polls(db_session, now=datetime.now(UTC)) == 0        # paused sources are not scheduled
