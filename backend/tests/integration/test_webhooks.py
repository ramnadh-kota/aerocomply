"""Signed generic webhook ingestion: authenticity, freshness, replay, tenant derivation, fail-closed behaviour."""
from __future__ import annotations

import json
import time
import uuid

import pytest
from sqlalchemy import select

from app.api.v1.webhooks import MAX_BODY_BYTES, sign
from app.core import secrets
from app.core.config import get_settings
from app.core.rate_limit_middleware import classify
from app.models.background_job import BackgroundJob, JobStatus
from app.models.hums import HUMSSensorReading
from app.services import job_handlers, job_service
from tests.integration.test_acquisition_pipeline import _drone, _org

SECRET = "whsec-unit-test-secret"


def _source(client, h, org_id, *, ctype="GENERIC_WEBHOOK", active=True, ref="webhook"):
    reference = f"datasource/{org_id}/{uuid.uuid4().hex[:6]}/{ref}"
    r = client.post("/api/v1/data-sources", headers=h, json={
        "name": f"wh-{uuid.uuid4().hex[:6]}", "connector_type": ctype, "connection_config": {},
        "secret_reference": reference})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    if active:
        assert client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": "ACTIVE"}).status_code == 200
    return sid, reference


def _post(client, sid, body: bytes, *, secret=SECRET, ts=None, sig=None, headers=None):
    ts = str(int(time.time())) if ts is None else str(ts)
    h = {"X-Kota-Timestamp": ts, "X-Kota-Signature": sig if sig is not None else sign(secret, ts, body),
         "Content-Type": "application/json", **(headers or {})}
    return client.post(f"/api/v1/webhooks/data-sources/{sid}", content=body, headers=h)


def _payload(asset_reg, value=1.0, when="2026-09-01T10:00:00Z"):
    return json.dumps({"events": [{"asset_id": asset_reg, "sensor_code": "TEMP", "value": value, "unit": "C",
                                   "timestamp": when}]}).encode()


@pytest.fixture
def env(client, db_session, monkeypatch):
    org_id, h = _org(client, db_session, "wh")
    _drone(client, h, reg="WH-1")
    sid, ref = _source(client, h, org_id)
    monkeypatch.setenv(secrets.env_name(ref), SECRET)
    return org_id, h, sid, ref


def test_valid_signed_webhook_is_queued_processed_and_attributed_to_the_sources_tenant(client, db_session, env):
    org_id, h, sid, _ = env
    r = _post(client, sid, _payload("WH-1"))
    assert r.status_code == 202 and r.json()["duplicate"] is False
    job = db_session.get(BackgroundJob, uuid.UUID(r.json()["job_id"]))
    assert job.organization_id == org_id and str(job.data_source_id) == sid and job.correlation_id == "webhook"
    assert job_service.run_one(db_session, worker_id="w", job_types=[job_handlers.INGEST])
    db_session.refresh(job)
    assert job.status == JobStatus.SUCCEEDED and job.result["accepted"] == 1
    assert db_session.scalar(select(HUMSSensorReading.id).where(HUMSSensorReading.organization_id == org_id)) is not None


def test_replay_is_acknowledged_but_never_processed_twice(client, db_session, env):
    _, _, sid, _ = env
    body, ts = _payload("WH-1"), int(time.time())
    first = _post(client, sid, body, ts=ts)
    again = _post(client, sid, body, ts=ts)
    assert first.status_code == 202 and again.status_code == 200
    assert again.json() == {"job_id": first.json()["job_id"], "status": "QUEUED", "duplicate": True}


@pytest.mark.parametrize("case", ["wrong_secret", "tampered_body", "no_signature", "garbage_signature", "bad_prefix",
                                  "stale", "future", "no_timestamp", "non_numeric_timestamp"])
def test_bad_requests_get_the_same_401_and_enqueue_nothing(client, db_session, env, case):
    _, _, sid, _ = env
    body, ts = _payload("WH-1"), int(time.time())
    before = db_session.scalar(select(BackgroundJob.id).where(BackgroundJob.job_type == job_handlers.INGEST).limit(1))
    if case == "wrong_secret":
        r = _post(client, sid, body, secret="not-the-secret")
    elif case == "tampered_body":
        r = _post(client, sid, body, sig=sign(SECRET, str(ts), body), ts=ts, headers=None) if False else \
            client.post(f"/api/v1/webhooks/data-sources/{sid}", content=body + b" ",
                        headers={"X-Kota-Timestamp": str(ts), "X-Kota-Signature": sign(SECRET, str(ts), body)})
    elif case == "no_signature":
        r = client.post(f"/api/v1/webhooks/data-sources/{sid}", content=body, headers={"X-Kota-Timestamp": str(ts)})
    elif case == "garbage_signature":
        r = _post(client, sid, body, sig="sha256=" + "0" * 64)
    elif case == "bad_prefix":
        r = _post(client, sid, body, sig=sign(SECRET, str(ts), body).replace("sha256=", "md5="))
    elif case == "stale":
        r = _post(client, sid, body, ts=ts - 3600)
    elif case == "future":
        r = _post(client, sid, body, ts=ts + 3600)
    elif case == "no_timestamp":
        r = client.post(f"/api/v1/webhooks/data-sources/{sid}", content=body, headers={"X-Kota-Signature": sign(SECRET, "", body)})
    else:
        r = _post(client, sid, body, ts="abc", sig=sign(SECRET, "abc", body))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_webhook"
    after = db_session.scalar(select(BackgroundJob.id).where(BackgroundJob.job_type == job_handlers.INGEST).limit(1))
    assert before == after


def test_unusable_sources_are_indistinguishable_from_bad_signatures(client, db_session, env, monkeypatch):
    org_id, h, sid, ref = env
    body = _payload("WH-1")
    responses = {}
    responses["unknown"] = _post(client, str(uuid.uuid4()), body)
    paused, pref = _source(client, h, org_id, active=False)
    monkeypatch.setenv(secrets.env_name(pref), SECRET)
    responses["draft"] = _post(client, paused, body)
    csv_src, cref = _source(client, h, org_id, ctype="CSV_BATCH")
    monkeypatch.setenv(secrets.env_name(cref), SECRET)
    responses["wrong_type"] = _post(client, csv_src, body)
    nosecret, _ = _source(client, h, org_id)                       # ACTIVE webhook whose secret env var is unset
    responses["no_secret"] = _post(client, nosecret, body)
    client.patch(f"/api/v1/data-sources/{sid}", headers=h, json={"status": "PAUSED"})
    responses["paused"] = _post(client, sid, body)
    for name, r in responses.items():
        assert r.status_code == 401 and r.json() == responses["unknown"].json(), name


def test_secret_of_one_source_does_not_authenticate_another_tenants_source(client, db_session, env, monkeypatch):
    org_a, ha, sid_a, _ = env
    org_b, hb = _org(client, db_session, "whb")
    sid_b, ref_b = _source(client, hb, org_b)
    monkeypatch.setenv(secrets.env_name(ref_b), "another-secret")
    assert _post(client, sid_b, _payload("WH-1"), secret=SECRET).status_code == 401       # A's secret on B's source
    assert _post(client, sid_b, _payload("WH-1"), secret="another-secret").status_code == 202


def test_oversized_and_empty_bodies(client, env):
    _, _, sid, _ = env
    assert _post(client, sid, b"").status_code == 422
    big = client.post(f"/api/v1/webhooks/data-sources/{sid}", content=b"x",
                      headers={"content-length": str(MAX_BODY_BYTES + 1), "X-Kota-Timestamp": "1", "X-Kota-Signature": "x"})
    assert big.status_code in (413, 400, 422)


def test_webhooks_share_the_webhook_rate_limit_policy(client, env):
    assert classify("POST", "/api/v1/webhooks/data-sources/abc") == "webhook"
    _, _, sid, _ = env
    s = get_settings()
    s.rate_limit_overrides = {"webhook": "3/60"}
    try:
        codes = [_post(client, sid, _payload("WH-1", when=f"2026-09-01T10:00:0{i}Z")).status_code for i in range(5)]
    finally:
        s.rate_limit_overrides = {}
    assert codes[:3] == [202, 202, 202] and codes[3:] == [429, 429]
