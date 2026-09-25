"""Integration test fixtures.

Requires a running Postgres instance (see infra/docker-compose.yml) and
TEST_DATABASE_URL set, e.g.:
    postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test

Schema is built by running the real Alembic migrations (not
Base.metadata.create_all) so DB-level constructs that live only in migrations
— e.g. the audit_events append-only trigger in 0002 — are actually present
during tests, not just the ORM-visible columns.

Each test runs inside a transaction that is rolled back afterward, so tests
never leak state into each other and never require manual cleanup.
"""

import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.deps import get_db_session
from app.core.rate_limit import reset_rate_limits
from app.core.security import hash_password
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """M17.2's rate limiter (app/core/rate_limit.py) is a single process-wide
    instance. Starlette's TestClient always presents the same fixed "IP"
    (its host is always "testclient"), so without this reset, one test's
    login/register/upload calls would count against a later, unrelated
    test's budget across this whole long-lived test process -- a purely
    test-infrastructure concern, never relevant in production where real
    clients have real, distinct IPs. Production code never calls this."""
    reset_rate_limits()
    yield


def _run_migrations(database_url: str, revision: str) -> None:
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_cfg, revision)


@pytest.fixture(scope="session")
def engine():
    _run_migrations(TEST_DATABASE_URL, "head")
    engine = create_engine(TEST_DATABASE_URL, future=True)
    yield engine
    _run_migrations(TEST_DATABASE_URL, "base")
    engine.dispose()


@pytest.fixture
def db_session(engine):
    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, future=True)
    session = SessionLocal()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


_PLATFORM_ADMIN_PASSWORD = "supersecret123"


def make_platform_admin_headers(client, db_session):
    """Bearer auth headers for a real, database-backed PLATFORM_ADMIN user.

    POST /auth/register-organization is gated behind Permission.PLATFORM_MANAGE
    (Phase 2 of the demo-access security work). Tests that use register-organization
    purely as a bootstrap fixture to stand up a fresh org+admin now need to call it
    as an authorized platform actor, exactly like a real caller would -- no
    test-only bypass. Mirrors the _create_platform_admin/_login pattern already
    used in test_provisioning.py. Plain function (not just a fixture) so helper
    functions like the many per-file `_register()` bootstraps can call it directly
    given the `client`/`db_session` they already have, without needing to thread a
    new fixture through every test function's signature.
    """
    org = Organization(name="Test Platform Ops")
    db_session.add(org)
    db_session.flush()
    admin = User(
        organization_id=org.id,
        email=f"platform-admin-{uuid.uuid4().hex[:12]}@example.com",
        hashed_password=hash_password(_PLATFORM_ADMIN_PASSWORD),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(admin)
    db_session.flush()
    db_session.add(UserRole(user_id=admin.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()

    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": admin.email, "password": _PLATFORM_ADMIN_PASSWORD},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def platform_admin_headers(client, db_session):
    return make_platform_admin_headers(client, db_session)
