"""Authentication foundation: email verification + forgot/reset password OTP.

Tests exercise the real HTTP endpoints (app/api/v1/auth.py) with the real
service layer (app/services/auth_service.py). The OTP code is captured by
monkeypatching app.services.auth_service.send_verification_code_email --
there is no real SMTP server in tests, and this is simpler/more reliable
than parsing log output (app/core/logging.py's configure_logging()
reassigns the root logger's handler list at app import time, which fights
pytest's caplog handler).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.rate_limit import reset_rate_limits
from app.models.auth_verification import AuthVerificationCode
from app.models.user import User


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


@pytest.fixture(autouse=True)
def _reset_limits():
    reset_rate_limits()
    yield
    reset_rate_limits()


@pytest.fixture
def captured_codes(monkeypatch):
    """Captures every OTP code that would have been emailed, keyed by
    recipient. auth_service imports send_verification_code_email directly
    (`from app.services.email_service import send_verification_code_email`),
    so the patch target is auth_service's own reference to it."""
    codes: dict[str, list[str]] = {}

    def _fake_send(*, to: str, code: str, purpose_label: str) -> None:
        codes.setdefault(to, []).append(code)

    monkeypatch.setattr("app.services.auth_service.send_verification_code_email", _fake_send)
    return codes


def _latest_code(captured_codes, email: str) -> str:
    return captured_codes[email][-1]


class TestEmailVerification:
    def test_request_and_confirm_email_verification(self, client, captured_codes):
        email = "verify-email-1@example.com"
        tokens = _register(client, "Verify Email Org", email)

        me_before = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()
        assert me_before["email_verified"] is False

        resp = client.post(
            "/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 200
        code = _latest_code(captured_codes, email)

        confirm = client.post(
            "/api/v1/auth/verify-email/confirm",
            headers=_auth(tokens["access_token"]),
            json={"code": code},
        )
        assert confirm.status_code == 200

        me_after = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()
        # Stale until next login/refresh (email_verified is baked into the
        # access token at issuance, see auth_service._issue_tokens) -- this
        # is the same known staleness as email/full_name already have.
        assert me_after["email_verified"] is False

        relogin = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "supersecret123"}
        )
        assert relogin.json()["access_token"]
        me_relogin = client.get(
            "/api/v1/auth/me", headers=_auth(relogin.json()["access_token"])
        ).json()
        assert me_relogin["email_verified"] is True

    def test_wrong_code_rejected(self, client, captured_codes):
        email = "verify-email-2@example.com"
        tokens = _register(client, "Verify Email Wrong Org", email)
        client.post("/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"]))

        resp = client.post(
            "/api/v1/auth/verify-email/confirm",
            headers=_auth(tokens["access_token"]),
            json={"code": "000000"},
        )
        assert resp.status_code == 401

    def test_already_verified_cannot_request_again(self, client, captured_codes):
        email = "verify-email-3@example.com"
        tokens = _register(client, "Verify Email Twice Org", email)
        client.post("/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"]))
        code = _latest_code(captured_codes, email)
        client.post(
            "/api/v1/auth/verify-email/confirm",
            headers=_auth(tokens["access_token"]),
            json={"code": code},
        )

        resp = client.post(
            "/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 409

    def test_resend_within_cooldown_rejected(self, client, captured_codes):
        tokens = _register(client, "Verify Email Resend Org", "verify-email-4@example.com")
        first = client.post(
            "/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"])
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"])
        )
        assert second.status_code == 409

    def test_confirm_without_auth_rejected(self, client):
        resp = client.post("/api/v1/auth/verify-email/confirm", json={"code": "123456"})
        assert resp.status_code == 401

    def test_max_attempts_exhausts_code(self, client, captured_codes):
        email = "verify-email-5@example.com"
        tokens = _register(client, "Verify Email Attempts Org", email)
        client.post("/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"]))
        code = _latest_code(captured_codes, email)

        for _ in range(5):
            resp = client.post(
                "/api/v1/auth/verify-email/confirm",
                headers=_auth(tokens["access_token"]),
                json={"code": "999999"},
            )
            assert resp.status_code == 401

        # The real code is now invalid too -- attempts exhausted.
        resp = client.post(
            "/api/v1/auth/verify-email/confirm",
            headers=_auth(tokens["access_token"]),
            json={"code": code},
        )
        assert resp.status_code == 401


class TestForgotPassword:
    def test_forgot_and_reset_password(self, client, captured_codes):
        email = "forgot-1@example.com"
        _register(client, "Forgot Password Org", email)

        resp = client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert resp.status_code == 200
        code = _latest_code(captured_codes, email)

        reset = client.post(
            "/api/v1/auth/reset-password",
            json={"email": email, "code": code, "new_password": "brandnewpassword123"},
        )
        assert reset.status_code == 200

        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "brandnewpassword123"}
        )
        assert login.status_code == 200

        old_login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "supersecret123"}
        )
        assert old_login.status_code == 401

    def test_forgot_password_nonexistent_email_returns_generic_success(
        self, client, captured_codes
    ):
        resp = client.post(
            "/api/v1/auth/forgot-password", json={"email": "no-such-user@example.com"}
        )
        assert resp.status_code == 200
        assert "message" in resp.json()
        assert captured_codes == {}

    def test_reset_password_wrong_code_rejected(self, client, captured_codes):
        email = "forgot-2@example.com"
        _register(client, "Forgot Password Wrong Org", email)
        client.post("/api/v1/auth/forgot-password", json={"email": email})

        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"email": email, "code": "000000", "new_password": "brandnewpassword123"},
        )
        assert resp.status_code == 401

    def test_reset_password_code_is_single_use(self, client, captured_codes):
        email = "forgot-3@example.com"
        _register(client, "Forgot Password Reuse Org", email)
        client.post("/api/v1/auth/forgot-password", json={"email": email})
        code = _latest_code(captured_codes, email)

        first = client.post(
            "/api/v1/auth/reset-password",
            json={"email": email, "code": code, "new_password": "firstnewpassword123"},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/v1/auth/reset-password",
            json={"email": email, "code": code, "new_password": "secondnewpassword123"},
        )
        assert second.status_code == 401

    def test_forgot_password_resend_cooldown(self, client, captured_codes):
        email = "forgot-4@example.com"
        _register(client, "Forgot Password Cooldown Org", email)
        first = client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert first.status_code == 200

        # Still a generic 200 -- request_password_reset() swallows the
        # cooldown ConflictError so the response never distinguishes "code
        # already sent recently" from "email doesn't exist" (same
        # anti-enumeration contract as the first request).
        second = client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert second.status_code == 200
        assert len(captured_codes[email]) == 1

    def test_reset_password_code_is_scoped_to_password_reset_purpose(self, client, captured_codes):
        """A code issued for email-verification must not work for password
        reset, even for the same user -- purposes are strictly isolated."""
        email = "forgot-5@example.com"
        tokens = _register(client, "Purpose Isolation Org", email)
        client.post("/api/v1/auth/verify-email/request", headers=_auth(tokens["access_token"]))
        verify_code = _latest_code(captured_codes, email)

        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"email": email, "code": verify_code, "new_password": "brandnewpassword123"},
        )
        assert resp.status_code == 401


class TestAuditAndStorage:
    def test_password_reset_records_audit_events(self, client, captured_codes, db_session):
        email = "audit-reset@example.com"
        _register(client, "Audit Reset Org", email)
        client.post("/api/v1/auth/forgot-password", json={"email": email})
        code = _latest_code(captured_codes, email)
        client.post(
            "/api/v1/auth/reset-password",
            json={"email": email, "code": code, "new_password": "brandnewpassword123"},
        )

        from app.models.audit_event import AuditEvent

        user = db_session.execute(select(User).where(User.email == email)).scalar_one()
        events = (
            db_session.execute(
                select(AuditEvent.action).where(
                    AuditEvent.entity_type == "User", AuditEvent.entity_id == user.id
                )
            )
            .scalars()
            .all()
        )
        assert "auth.password_reset_requested" in events
        assert "auth.password_reset_completed" in events

    def test_code_is_never_stored_in_plaintext(self, client, captured_codes, db_session):
        email = "hash-check@example.com"
        _register(client, "Hash Check Org", email)
        client.post("/api/v1/auth/forgot-password", json={"email": email})
        code = _latest_code(captured_codes, email)

        user = db_session.execute(select(User).where(User.email == email)).scalar_one()
        row = db_session.execute(
            select(AuthVerificationCode).where(AuthVerificationCode.user_id == user.id)
        ).scalar_one()
        assert row.code_hash != code
        assert code not in row.code_hash


class TestTenantIsolation:
    def test_verification_code_table_has_no_organization_scoping(self):
        # auth_verification_codes is keyed by user_id only (CASCADE from
        # users), not organization_id -- correct, since it's always
        # resolved through a specific user, and User itself already carries
        # tenant scoping (TenantScopedMixin). No separate tenant check is
        # needed or added here.
        assert not hasattr(AuthVerificationCode, "organization_id")


class TestUnknownUser:
    def test_request_email_verification_for_nonexistent_user_id(self, db_session):
        from app.services import auth_service

        with pytest.raises(Exception) as exc_info:
            auth_service.request_email_verification(db_session, user_id=uuid.uuid4())
        assert "not found" in str(exc_info.value).lower()
