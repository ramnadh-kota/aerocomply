"""Policy rate limiting: ingest / LISA / admin / default limits, tenant keying, overrides, fail-safe, metrics."""
import uuid

import pytest

from app.core import rate_limit_middleware as rlm
from app.core.config import live_settings
from app.core.metrics import REGISTRY
from app.core.rate_limit import reset_rate_limits
from tests.integration.test_acquisition_pipeline import _org, _source

settings = live_settings
pytestmark = pytest.mark.usefixtures("db_session")


@pytest.fixture(autouse=True)
def _clean():
    reset_rate_limits()
    yield
    settings.rate_limit_overrides = {}
    reset_rate_limits()


def test_classification():
    c = rlm.classify
    assert c("POST", "/api/v1/auth/login") is None            # governed by the per-route dependency
    assert c("GET", "/health") is None
    assert c("POST", "/api/v1/data-sources/abc/ingest") == "ingest"
    assert c("POST", "/api/v1/telemetry/dji/webhook") == "webhook"
    assert c("POST", "/api/v1/lisa/ask") == "lisa"
    assert c("GET", "/api/v1/platform/organizations") == "admin"
    assert c("GET", "/api/v1/hums/assets/x/health") == "analytics"
    assert c("GET", "/api/v1/drones") == "default"


def test_ingest_limit_is_per_tenant_and_returns_429_with_retry_after(client, db_session):
    settings.rate_limit_overrides = {"ingest": "3/60"}
    _, h1 = _org(client, db_session, "rl1")
    _, h2 = _org(client, db_session, "rl2")
    s1, s2 = _source(client, h1, "CSV_BATCH"), _source(client, h2, "CSV_BATCH")
    body = b"asset_id,sensor_code,value,unit,timestamp\n"
    codes1 = [client.post(f"/api/v1/data-sources/{s1}/ingest", headers=h1, content=body).status_code for _ in range(5)]
    assert codes1.count(429) == 2 and 429 not in codes1[:3]
    r = client.post(f"/api/v1/data-sources/{s1}/ingest", headers=h1, content=body)
    assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
    assert r.json()["error"]["code"] == "rate_limited"
    # another tenant is unaffected
    assert client.post(f"/api/v1/data-sources/{s2}/ingest", headers=h2, content=body).status_code != 429


def test_lisa_limit_is_per_user(client, db_session):
    settings.rate_limit_overrides = {"lisa": "2/60"}
    _, h = _org(client, db_session, "rl3")
    codes = [client.post("/api/v1/lisa/ask", headers=h, json={"message": "hi"}).status_code for _ in range(4)]
    assert codes[2:] == [429, 429] and 429 not in codes[:2]


def test_unauthenticated_requests_are_keyed_by_ip_and_cannot_dodge_with_garbage_tokens(client):
    settings.rate_limit_overrides = {"default": "2/60"}
    codes = [client.get("/api/v1/drones", headers={"Authorization": f"Bearer junk{i}"}).status_code for i in range(4)]
    assert codes[2:] == [429, 429]          # varying the bad token does not create a fresh bucket


def test_forged_forwarded_for_is_ignored_by_default(client):
    settings.rate_limit_overrides = {"default": "2/60"}
    codes = [client.get("/api/v1/drones", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(4)]
    assert codes[2:] == [429, 429]


def test_policy_can_be_disabled_and_bad_override_keeps_safe_default(client):
    settings.rate_limit_overrides = {"default": "off"}
    assert all(client.get("/api/v1/drones").status_code != 429 for _ in range(30))
    assert rlm.resolve("default") is None
    settings.rate_limit_overrides = {"lisa": "garbage"}
    assert rlm.resolve("lisa") == (30, 60, "user")
    settings.rate_limit_overrides = {"lisa": "-5/60"}
    assert rlm.resolve("lisa") == (30, 60, "user")


def test_master_switch(client):
    settings.rate_limit_overrides = {"default": "1/60"}
    settings.rate_limit_enabled = False
    try:
        assert all(client.get("/api/v1/drones").status_code != 429 for _ in range(5))
    finally:
        settings.rate_limit_enabled = True


def test_limiter_internal_error_fails_open(client, monkeypatch):
    from app.core import rate_limit as rl

    class Broken:
        def check(self, *a, **k):
            raise RuntimeError("limiter down")

        def reset(self):
            pass

    monkeypatch.setattr(rl, "_limiter", Broken())
    # Fail-open policy ("default"): the shared store is down, the request is still served (local fallback count).
    assert client.get("/api/v1/drones").status_code != 429
    assert 'kota_rate_limit_backend_errors_total{outcome="local_fallback",policy="default"}' in REGISTRY.render()


def test_rejections_are_counted_in_metrics(client):
    settings.rate_limit_overrides = {"default": "1/60"}
    client.get("/api/v1/drones"); client.get("/api/v1/drones")
    assert 'kota_rate_limited_total{policy="default"}' in REGISTRY.render()
