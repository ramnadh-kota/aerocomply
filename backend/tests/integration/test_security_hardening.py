"""Authentication / authorization hardening: token authority, JWT forgery, CORS, headers, injection, mass assignment."""
from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import timedelta

import pytest
from jose import jwt
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User, UserRole
from tests.integration.test_acquisition_pipeline import _drone, _org

settings = get_settings()


def _me(client, h):
    return client.get("/api/v1/auth/me", headers=h)


def _user_of(client, db, h) -> User:
    return db.get(User, uuid.UUID(_me(client, h).json()["id"]))


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _b64(obj) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


# ------------------------------------------------------------------ the database is the authority
def test_deactivated_user_loses_access_immediately_not_at_token_expiry(client, db_session):
    org_id, h = _org(client, db_session, "deact")
    assert _me(client, h).status_code == 200
    _user_of(client, db_session, h).is_active = False
    db_session.flush()
    r = _me(client, h)
    assert r.status_code == 401 and client.get("/api/v1/drones", headers=h).status_code == 401


def test_revoked_role_takes_effect_on_the_next_request(client, db_session):
    org_id, h = _org(client, db_session, "revoke")
    _drone(client, h, reg="REV-1")                                        # ORG_ADMIN can write
    user = _user_of(client, db_session, h)
    db_session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db_session.flush()
    assert client.post("/api/v1/drones", headers=h, json={"registration": "REV-2"}).status_code == 403
    assert client.get("/api/v1/drones", headers=h).status_code == 403


def test_token_role_claim_cannot_escalate_privileges(client, db_session):
    org_id, h = _org(client, db_session, "escal")
    user = _user_of(client, db_session, h)
    db_session.execute(delete(UserRole).where(UserRole.user_id == user.id))
    db_session.add(UserRole(user_id=user.id, role_name="VIEWER", organization_id=org_id))
    db_session.flush()
    forged_claims = create_access_token(user.id, org_id, ["PLATFORM_ADMIN", "ORG_ADMIN"], email=user.email)
    assert client.get("/api/v1/platform/organizations", headers=_bearer(forged_claims)).status_code == 403
    assert client.post("/api/v1/drones", headers=_bearer(forged_claims), json={"registration": "ESC-1"}).status_code == 403


def test_user_cannot_use_a_token_for_another_organization(client, db_session):
    org_a, ha = _org(client, db_session, "xorg1")
    org_b, hb = _org(client, db_session, "xorg2")
    ua = _user_of(client, db_session, ha)
    cross = create_access_token(ua.id, org_b, ["ORG_ADMIN"], email=ua.email)     # right user, wrong tenant
    assert client.get("/api/v1/drones", headers=_bearer(cross)).status_code == 401


def test_token_for_a_nonexistent_user_is_rejected(client, db_session):
    org_id, _ = _org(client, db_session, "ghost")
    ghost = create_access_token(uuid.uuid4(), org_id, ["ORG_ADMIN"])
    assert client.get("/api/v1/drones", headers=_bearer(ghost)).status_code == 401


# ------------------------------------------------------------------ JWT forgery
def test_jwt_forgeries_are_rejected(client, db_session):
    org_id, h = _org(client, db_session, "jwt")
    user = _user_of(client, db_session, h)
    good = h["Authorization"].split()[1]
    header, payload, sig = good.split(".")
    tampered_payload = json.loads(base64.urlsafe_b64decode(payload + "=="))
    tampered_payload["roles"] = ["PLATFORM_ADMIN"]
    cases = {
        "alg=none": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{payload}.",
        "alg=none, empty sig, admin": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(tampered_payload)}.",
        "tampered payload, old signature": f"{header}.{_b64(tampered_payload)}.{sig}",
        "wrong secret": jwt.encode({**tampered_payload, "exp": int(time.time()) + 600}, "not-the-secret", algorithm="HS256"),
        "garbage": "not.a.jwt",
        "empty": "",
        "truncated signature": good[:-6],
    }
    for name, token in cases.items():
        assert client.get("/api/v1/drones", headers=_bearer(token)).status_code == 401, name
    assert client.get("/api/v1/drones", headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get("/api/v1/drones").status_code == 401


def test_expired_and_wrong_type_tokens_are_rejected(client, db_session):
    org_id, h = _org(client, db_session, "exp")
    user = _user_of(client, db_session, h)
    now = int(time.time())
    base = {"sub": str(user.id), "organization_id": str(org_id), "roles": ["ORG_ADMIN"], "type": "access"}
    expired = jwt.encode({**base, "exp": now - 5}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    no_exp = jwt.encode(base, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert client.get("/api/v1/drones", headers=_bearer(expired)).status_code == 401
    assert client.get("/api/v1/drones", headers=_bearer(no_exp)).status_code == 401           # no expiry => invalid
    refresh = create_refresh_token(user.id, org_id)
    assert client.get("/api/v1/drones", headers=_bearer(refresh)).status_code == 401           # refresh != access
    wrong_type = jwt.encode({**base, "type": "password_reset", "exp": now + 600}, settings.jwt_secret_key,
                            algorithm=settings.jwt_algorithm)
    assert client.get("/api/v1/drones", headers=_bearer(wrong_type)).status_code == 401


# ------------------------------------------------------------------ transport / browser surface
def test_cors_does_not_reflect_untrusted_origins_and_login_sets_no_cookies(client):
    evil = client.options("/api/v1/auth/login", headers={"Origin": "https://evil.example",
                                                         "Access-Control-Request-Method": "POST"})
    assert evil.headers.get("access-control-allow-origin") != "https://evil.example"
    assert "*" != evil.headers.get("access-control-allow-origin")
    good = client.options("/api/v1/auth/login", headers={"Origin": settings.cors_allow_origins[0],
                                                         "Access-Control-Request-Method": "POST"})
    assert good.headers.get("access-control-allow-origin") == settings.cors_allow_origins[0]
    r = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x" * 12})
    assert "set-cookie" not in r.headers          # bearer-token API: no ambient credentials => no CSRF surface


def test_security_headers_and_json_only_error_bodies(client):
    r = client.get("/health")
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h.get("x-content-type-options") == "nosniff"
    assert "frame-ancestors" in h.get("content-security-policy", "") or h.get("x-frame-options")
    bad = client.get("/api/v1/drones/<script>alert(1)</script>")
    assert bad.headers["content-type"].startswith("application/json")           # reflected input is never served as HTML
    assert "<script>" not in bad.text or bad.headers["content-type"].startswith("application/json")


# ------------------------------------------------------------------ injection / mass assignment
@pytest.mark.parametrize("payload", ["' OR '1'='1", "'; DROP TABLE assets;--", "%' UNION SELECT NULL--", "\\x00", "🙂" * 50])
def test_search_and_filter_parameters_are_parameterised(client, db_session, payload):
    org_id, h = _org(client, db_session, "sqli")
    _drone(client, h, reg="SAFE-1")
    r = client.get("/api/v1/assets", headers=h, params={"search": payload, "status": payload, "asset_type": payload})
    assert r.status_code == 200 and r.json() == []
    assert len(client.get("/api/v1/assets", headers=h).json()) == 1               # table intact


def test_mass_assignment_on_profile_update_is_ignored(client, db_session):
    org_id, h = _org(client, db_session, "mass")
    other_org, _ = _org(client, db_session, "mass2")
    user = _user_of(client, db_session, h)
    before_roles = set(db_session.execute(select(UserRole.role_name).where(UserRole.user_id == user.id)).scalars())
    r = client.patch("/api/v1/auth/me", headers=h, json={
        "full_name": "Renamed", "roles": ["PLATFORM_ADMIN"], "organization_id": str(other_org), "is_active": False,
        "email_verified": True, "hashed_password": "x", "id": str(uuid.uuid4())})
    assert r.status_code in (200, 422)
    db_session.refresh(user)
    assert user.organization_id == org_id and user.is_active is True
    assert set(db_session.execute(select(UserRole.role_name).where(UserRole.user_id == user.id)).scalars()) == before_roles
    assert user.hashed_password != "x"


def test_asset_create_ignores_client_supplied_tenant_and_id(client, db_session):
    org_id, h = _org(client, db_session, "mass3")
    other_org, _ = _org(client, db_session, "mass4")
    r = client.post("/api/v1/drones", headers=h, json={"registration": "MASS-1", "organization_id": str(other_org)})
    assert r.status_code == 201 and r.json()["organization_id"] == str(org_id)


# ------------------------------------------------------------------ nothing sensitive reaches the logs
def test_logs_never_contain_passwords_tokens_secrets_or_raw_telemetry(client, db_session, caplog, capsys, monkeypatch):
    import logging

    from app.core import secrets
    from app.listeners.mqtt import validate_mqtt_config

    caplog.set_level(logging.DEBUG)
    org_id, h = _org(client, db_session, "logs")
    token = h["Authorization"].split()[1]
    password = "Sup3r-Secret-Passw0rd!"
    monkeypatch.setenv(secrets.env_name("datasource/logs/mqtt"), "MQTT-BROKER-SECRET-VALUE")
    validate_mqtt_config({"listen": {"host": "localhost", "topics": ["a/#"], "username": "u"}}, "datasource/logs/mqtt")

    client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": password})     # failed login
    _drone(client, h, reg="LOG-1")
    marker = "RAW-TELEMETRY-MARKER-9f3a"
    from tests.integration.test_acquisition_pipeline import _csv, _ingest, _source

    sid = _source(client, h, "CSV_BATCH")
    _ingest(client, h, sid, _csv([{"asset_id": "LOG-1", "sensor_code": marker, "value": "1", "unit": "C",
                                   "timestamp": "2026-09-01T10:00:00Z"}]))
    client.get("/api/v1/drones", headers={"Authorization": "Bearer " + token + "tampered"})            # rejected token

    out = capsys.readouterr()
    blob = caplog.text + out.out + out.err
    for needle in (password, token, "MQTT-BROKER-SECRET-VALUE", marker, "M20Preview"):
        assert needle not in blob, f"sensitive value leaked into logs: {needle[:12]}..."
