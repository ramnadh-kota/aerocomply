"""Tests for M13: the platform health/monitoring read API (GET /platform/health).

Covers the service (app/services/platform_health_service) and the HTTP
route (app/api/v1/platform.py). This is deliberately a thin, on-demand
health snapshot -- not a metrics/telemetry platform -- so tests focus on:
authorization, deterministic status calculation, no secret leakage, and
schema shape.
"""
from app.core.deps import get_db_session
from app.core.security import hash_password
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.platform_health_service import HealthStatus, get_platform_health


def _create_platform_admin(db_session, email):
    org = Organization(name="Platform Health Ops")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()
    return user


def _login(client, email):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "supersecret123"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_get_platform_health_reports_healthy_when_db_reachable(db_session):
    snapshot = get_platform_health(db_session)
    assert snapshot.overall_status == HealthStatus.HEALTHY
    names = {c.name for c in snapshot.components}
    expected = {"api", "database", "entitlement_service", "audit_service", "background_workers"}
    assert expected <= names


def test_platform_health_status_calculation_is_deterministic(db_session):
    # Calling twice with a healthy DB must yield the same overall status --
    # no randomness, no time-based flakiness.
    first = get_platform_health(db_session)
    second = get_platform_health(db_session)
    assert first.overall_status == second.overall_status == HealthStatus.HEALTHY


def test_background_workers_reported_not_applicable_never_fabricated_healthy(db_session):
    snapshot = get_platform_health(db_session)
    workers = next(c for c in snapshot.components if c.name == "background_workers")
    assert workers.status == HealthStatus.NOT_APPLICABLE


def test_dependent_services_derive_status_from_database_not_independently_fabricated(db_session):
    snapshot = get_platform_health(db_session)
    db_component = next(c for c in snapshot.components if c.name == "database")
    entitlement_component = next(c for c in snapshot.components if c.name == "entitlement_service")
    audit_component = next(c for c in snapshot.components if c.name == "audit_service")
    assert entitlement_component.status == db_component.status
    assert audit_component.status == db_component.status


def test_get_platform_health_is_read_only(db_session):
    from app.models.audit_event import AuditEvent

    before = db_session.query(AuditEvent).count()
    get_platform_health(db_session)
    after = db_session.query(AuditEvent).count()
    assert before == after


# ---------------------------------------------------------------------------
# HTTP route tests
# ---------------------------------------------------------------------------


def test_platform_admin_can_get_health_via_api(client, db_session):
    _create_platform_admin(db_session, "health-ops@kotas-aerospace-internal.com")
    headers = _login(client, "health-ops@kotas-aerospace-internal.com")
    resp = client.get("/api/v1/platform/health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] == "HEALTHY"
    assert "checked_at" in body
    assert isinstance(body["components"], list) and len(body["components"]) >= 4
    for component in body["components"]:
        assert set(component.keys()) >= {"name", "status", "detail"}


def test_non_platform_admin_gets_403_from_health_endpoint(client):
    tokens = _register(client, "Health Read Customer", "admin@health-read-customer.com")
    resp = client.get(
        "/api/v1/platform/health", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp.status_code == 403


def test_unauthenticated_request_is_rejected(client):
    resp = client.get("/api/v1/platform/health")
    assert resp.status_code in (401, 403)


def test_health_response_never_leaks_connection_string_or_secrets(client, db_session):
    _create_platform_admin(db_session, "health-secrets@kotas-aerospace-internal.com")
    headers = _login(client, "health-secrets@kotas-aerospace-internal.com")
    resp = client.get("/api/v1/platform/health", headers=headers)
    body_text = resp.text.lower()
    for forbidden in ("postgresql://", "password", "secret_key", "jwt_secret"):
        assert forbidden not in body_text
