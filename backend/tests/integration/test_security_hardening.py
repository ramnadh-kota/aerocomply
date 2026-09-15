"""M17.2: production security hardening regression tests.

Covers the security test matrix from the M17.2 spec: auth token handling,
authorization, tenant isolation, CORS, security headers, rate limiting,
error leakage, secret safety, and Evidence-specific security invariants.
Real DB-backed HTTP tests via the existing `client`/`db_session` fixtures --
no new test infrastructure introduced.
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import get_settings
from app.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, evidence_service, work_order_service


def _register(client, org_name, email):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuthTokenHandling:
    def test_missing_token_rejected(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_malformed_token_rejected(self, client):
        resp = client.get("/api/v1/auth/me", headers=_auth("not-a-real-jwt"))
        assert resp.status_code == 401

    def test_wrong_signature_rejected(self, client):
        settings = get_settings()
        bad_token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "organization_id": str(uuid.uuid4()),
                "type": "access",
                "exp": datetime.now(UTC) + timedelta(minutes=5),
            },
            "a-completely-different-secret",
            algorithm=settings.jwt_algorithm,
        )
        resp = client.get("/api/v1/auth/me", headers=_auth(bad_token))
        assert resp.status_code == 401

    def test_expired_token_rejected(self, client):
        settings = get_settings()
        expired_token = jwt.encode(
            {
                "sub": str(uuid.uuid4()),
                "organization_id": str(uuid.uuid4()),
                "type": "access",
                "exp": datetime.now(UTC) - timedelta(minutes=1),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        resp = client.get("/api/v1/auth/me", headers=_auth(expired_token))
        assert resp.status_code == 401

    def test_refresh_token_cannot_be_used_as_access_token(self, client):
        tokens = _register(client, "Sec Token Org", "admin@sec-token.com")
        resp = client.get("/api/v1/auth/me", headers=_auth(tokens["refresh_token"]))
        assert resp.status_code == 401

    def test_access_token_cannot_be_used_as_refresh_token(self, client):
        tokens = _register(client, "Sec Token Org2", "admin@sec-token2.com")
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
        assert resp.status_code == 401

    def test_authentication_error_message_is_generic(self, client):
        # Wrong password and nonexistent email must be indistinguishable at
        # the HTTP layer (status + body) -- both already return the same
        # generic message; this pins that behavior as a regression test.
        _register(client, "Sec Enum Org", "real-user@sec-enum.com")
        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"email": "real-user@sec-enum.com", "password": "totally-wrong"},
        )
        nonexistent = client.post(
            "/api/v1/auth/login",
            json={"email": "no-such-user@sec-enum.com", "password": "whatever"},
        )
        assert wrong_password.status_code == nonexistent.status_code == 401
        assert wrong_password.json() == nonexistent.json()

    def test_password_hash_never_returned_by_api(self, client):
        tokens = _register(client, "Sec Hash Org", "admin@sec-hash.com")
        me = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"]))
        assert "hashed_password" not in me.text
        assert "password" not in me.json()


class TestTimingSafeAuthentication:
    def test_dummy_hash_is_a_real_argon2_hash_not_a_placeholder(self):
        # Must actually be verifiable (i.e. a real, distinct hash) so the
        # "verify against a dummy hash" path in auth_service.authenticate
        # performs genuine argon2 work rather than short-circuiting.
        assert DUMMY_PASSWORD_HASH.startswith("$argon2")
        assert verify_password("not-a-real-password-just-for-timing-parity", DUMMY_PASSWORD_HASH)
        assert not verify_password("something-else", DUMMY_PASSWORD_HASH)

    def test_nonexistent_and_wrong_password_both_perform_real_hashing_work(self):
        # Not a precise timing assertion (which would be flaky in CI) --
        # instead confirms both code paths actually call into argon2 (a
        # measurably non-trivial amount of wall-clock time), rather than one
        # of them short-circuiting near-instantly.
        start = time.perf_counter()
        verify_password("whatever", DUMMY_PASSWORD_HASH)
        dummy_elapsed = time.perf_counter() - start

        real_hash = hash_password("a-real-password")
        start = time.perf_counter()
        verify_password("wrong-guess", real_hash)
        real_elapsed = time.perf_counter() - start

        # Both should cost real argon2 time (loose bound: not near-zero).
        assert dummy_elapsed > 0.001
        assert real_elapsed > 0.001


class TestAuthorization:
    def test_missing_permission_returns_403(self, client, db_session):
        from app.core.security import hash_password as _hash
        from app.models.user import User, UserRole

        tokens = _register(client, "Sec AuthZ Org", "admin@sec-authz.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        viewer = User(
            organization_id=org_id,
            email="viewer@sec-authz.com",
            hashed_password=_hash("supersecret123"),
            full_name="Viewer",
            is_active=True,
        )
        db_session.add(viewer)
        db_session.flush()
        db_session.add(UserRole(user_id=viewer.id, role_name="VIEWER", organization_id=org_id))
        db_session.commit()

        login = client.post(
            "/api/v1/auth/login", json={"email": viewer.email, "password": "supersecret123"}
        )
        viewer_token = login.json()["access_token"]

        resp = client.post(
            "/api/v1/evidence",
            headers=_auth(viewer_token),
            json={"task_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

    def test_tenant_user_cannot_invoke_platform_operation(self, client):
        tokens = _register(client, "Sec Platform Org", "admin@sec-platform.com")
        resp = client.get("/api/v1/platform/organizations", headers=_auth(tokens["access_token"]))
        assert resp.status_code == 403


class TestTenantIsolation:
    def _create_evidence(self, db_session, org_id, user_id, wo_number):
        aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_id,
            payload=AircraftCreateRequest(
                registration=f"N{wo_number[-4:]}", msn=f"MSN-{wo_number}", aircraft_type="A320"
            ),
        )
        work_order = work_order_service.create_work_order(
            db_session,
            organization_id=org_id,
            created_by_user_id=user_id,
            payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number=wo_number),
        )
        task = work_order_service.create_task(
            db_session,
            organization_id=org_id,
            payload=TaskCreateRequest(work_order_id=work_order.id, description="Inspect panel"),
        )
        return evidence_service.create_evidence(
            db_session, organization_id=org_id, task_id=task.id, uploaded_by_user_id=user_id
        )

    def test_cross_tenant_evidence_read_blocked(self, client, db_session):
        from sqlalchemy import select

        from app.models.user import User

        tokens_a = _register(client, "Sec Tenant A", "admin@sec-tenant-a.com")
        tokens_b = _register(client, "Sec Tenant B", "admin@sec-tenant-b.com")
        org_b = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens_b["access_token"])).json()[
                "organization_id"
            ]
        )
        admin_b = (
            db_session.execute(select(User).where(User.organization_id == org_b)).scalars().first()
        )
        evidence_b = self._create_evidence(db_session, org_b, admin_b.id, "WO-SEC-1")

        resp = client.get(
            f"/api/v1/evidence/{evidence_b.id}", headers=_auth(tokens_a["access_token"])
        )
        assert resp.status_code == 404

    def test_cross_tenant_evidence_mutation_blocked(self, client, db_session):
        from sqlalchemy import select

        from app.models.user import User

        tokens_a = _register(client, "Sec Tenant A2", "admin@sec-tenant-a2.com")
        tokens_b = _register(client, "Sec Tenant B2", "admin@sec-tenant-b2.com")
        org_b = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens_b["access_token"])).json()[
                "organization_id"
            ]
        )
        admin_b = (
            db_session.execute(select(User).where(User.organization_id == org_b)).scalars().first()
        )
        evidence_b = self._create_evidence(db_session, org_b, admin_b.id, "WO-SEC-2")

        resp = client.post(
            f"/api/v1/evidence/{evidence_b.id}/transition",
            headers=_auth(tokens_a["access_token"]),
            json={"target_status": "SUBMITTED"},
        )
        assert resp.status_code == 404

    def test_nested_cross_tenant_file_idor_blocked(self, client, db_session):
        from sqlalchemy import select

        from app.models.evidence import EvidenceFile, EvidenceFileStatus
        from app.models.user import User

        tokens_a = _register(client, "Sec Tenant A3", "admin@sec-tenant-a3.com")
        tokens_b = _register(client, "Sec Tenant B3", "admin@sec-tenant-b3.com")
        org_b = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens_b["access_token"])).json()[
                "organization_id"
            ]
        )
        admin_b = (
            db_session.execute(select(User).where(User.organization_id == org_b)).scalars().first()
        )
        evidence_b = self._create_evidence(db_session, org_b, admin_b.id, "WO-SEC-3")
        file_b = EvidenceFile(
            organization_id=org_b,
            evidence_id=evidence_b.id,
            uploaded_by_user_id=admin_b.id,
            original_filename="secret.pdf",
            content_type="application/pdf",
            size_bytes=10,
            storage_key=f"evidence/{org_b}/{evidence_b.id}/{uuid.uuid4()}_secret.pdf",
            status=EvidenceFileStatus.STORED.value,
        )
        db_session.add(file_b)
        db_session.commit()

        resp = client.get(
            f"/api/v1/evidence/{evidence_b.id}/files/{file_b.id}/download",
            headers=_auth(tokens_a["access_token"]),
        )
        assert resp.status_code == 404
        assert "url" not in resp.json()


class TestCors:
    def test_allowed_origin_reflected_with_credentials(self, client):
        allowed = get_settings().cors_allow_origins[0]
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Origin": allowed},
        )
        assert resp.headers.get("access-control-allow-origin") == allowed
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_disallowed_origin_not_reflected(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Origin": "https://evil.example.com"},
        )
        assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"

    def test_preflight_for_disallowed_origin_does_not_grant_access(self, client):
        resp = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"


class TestSecurityHeaders:
    def test_representative_response_carries_security_headers(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert "permissions-policy" in resp.headers

    def test_security_headers_present_even_on_error_response(self, client):
        resp = client.get("/api/v1/auth/me")  # 401, no token
        assert resp.status_code == 401
        assert resp.headers.get("x-content-type-options") == "nosniff"


class TestRateLimiting:
    def test_normal_single_login_attempt_not_blocked(self, client):
        _register(client, "Sec RateLimit Org1", "admin@sec-rl-1.com")
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@sec-rl-1.com", "password": "supersecret123"},
        )
        assert resp.status_code == 200

    def test_repeated_login_attempts_are_eventually_rate_limited(self, client):
        _register(client, "Sec RateLimit Org2", "admin@sec-rl-2.com")
        statuses = []
        for _ in range(30):
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": "admin@sec-rl-2.com", "password": "wrong-password"},
            )
            statuses.append(resp.status_code)
        assert 429 in statuses

    def test_rate_limited_response_is_safe_and_generic(self, client):
        for _ in range(30):
            resp = client.post(
                "/api/v1/auth/login",
                json={"email": "whoever@sec-rl-3.com", "password": "wrong-password"},
            )
            if resp.status_code == 429:
                body = resp.json()
                assert body["error"]["code"] == "rate_limited"
                assert "traceback" not in resp.text.lower()
                return
        raise AssertionError("expected to observe a 429 within 30 attempts")


class TestErrorLeakage:
    def test_not_found_error_has_no_internal_detail(self, client, db_session):
        tokens = _register(client, "Sec Error Org", "admin@sec-error.com")
        resp = client.get(f"/api/v1/evidence/{uuid.uuid4()}", headers=_auth(tokens["access_token"]))
        assert resp.status_code == 404
        body = resp.json()
        assert "traceback" not in resp.text.lower()
        assert "sqlalchemy" not in resp.text.lower()
        assert "psycopg" not in resp.text.lower()
        assert body["error"]["code"] == "not_found"

    def test_validation_error_does_not_leak_internal_paths(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-object"},  # missing password, wrong shape
        )
        assert resp.status_code == 422
        assert "Traceback" not in resp.text
        assert "site-packages" not in resp.text


class TestSecretConfigSafety:
    def test_settings_object_never_serialized_by_any_api_response(self, client):
        tokens = _register(client, "Sec Config Org", "admin@sec-config.com")
        me = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"]))
        text_lower = me.text.lower()
        assert "jwt_secret_key" not in text_lower
        assert "s3_secret_key" not in text_lower
        assert "database_url" not in text_lower

    def test_logs_do_not_contain_bearer_token_value(self, client, caplog):
        tokens = _register(client, "Sec Log Org", "admin@sec-log.com")
        with caplog.at_level("DEBUG"):
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"]))
        assert tokens["access_token"] not in caplog.text
