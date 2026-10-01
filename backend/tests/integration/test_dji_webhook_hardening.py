"""DJI FlightHub webhook hardening: bounded body, generic malformed-payload error, fail-closed ordering."""
import hashlib
import hmac
import json
from types import SimpleNamespace

from app.api.v1 import telemetry as telemetry_api
from tests.integration.test_acquisition_pipeline import _org

SECRET = "hardening-secret"


def _sig(raw: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def _use_secret(monkeypatch):
    monkeypatch.setattr(telemetry_api, "get_settings", lambda: SimpleNamespace(dji_webhook_secret=SECRET))


def test_oversized_bodies_are_refused_before_authentication(client, db_session, monkeypatch):
    _use_secret(monkeypatch)
    big = b"x" * (telemetry_api.DJI_WEBHOOK_MAX_BODY_BYTES + 1)
    # no signature at all: still 413, not 401 -- we never buffered or hashed the body
    assert client.post("/api/v1/telemetry/dji/webhook", content=big).status_code == 413
    # chunked upload without a declared length is capped while streaming
    def gen():
        for _ in range(telemetry_api.DJI_WEBHOOK_MAX_BODY_BYTES // 65536 + 2):
            yield b"y" * 65536
    assert client.post("/api/v1/telemetry/dji/webhook", content=gen()).status_code == 413


def test_malformed_payload_gets_a_generic_422_that_does_not_echo_parser_internals(client, db_session, monkeypatch):
    org_id, _ = _org(client, db_session, "djih")
    _use_secret(monkeypatch)
    for raw in (b"not json at all", json.dumps({"unexpected": True}).encode(), b"[1,2,3]"):
        r = client.post("/api/v1/telemetry/dji/webhook", content=raw,
                        headers={"Content-Type": "application/json", "X-Organization-ID": str(org_id), "X-DJI-Signature": _sig(raw)})
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Malformed DJI webhook payload"


def test_small_valid_size_body_still_reaches_authentication(client, monkeypatch):
    _use_secret(monkeypatch)
    raw = b"{}"
    assert client.post("/api/v1/telemetry/dji/webhook", content=raw).status_code == 401
