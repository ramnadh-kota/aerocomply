"""Integration test fixtures.

Requires a running Postgres instance (see infra/docker-compose.yml). Configure with
TEST_DATABASE_URL, or TEST_DB_HOST/PORT/USER/PASSWORD/NAME (default port 5432), e.g.:
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
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.deps import get_db_session
from app.core.rate_limit import reset_rate_limits
from app.core.security import hash_password
from app.main import app
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.product_catalog import ProductSuite
from app.models.user import User, UserRole

def _resolve_test_database_url() -> str:
    """TEST_DATABASE_URL wins; otherwise build it from TEST_DB_HOST/PORT/USER/
    PASSWORD/NAME (defaults match infra/docker-compose.yml: localhost:5432). A
    native Postgres on another port (e.g. 55432) only needs TEST_DB_PORT."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    user = os.environ.get("TEST_DB_USER", "aerocomply")
    password = os.environ.get("TEST_DB_PASSWORD", "aerocomply")
    host = os.environ.get("TEST_DB_HOST", "localhost")
    port = os.environ.get("TEST_DB_PORT", "5432")
    name = os.environ.get("TEST_DB_NAME", "aerocomply_test")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


TEST_DATABASE_URL = _resolve_test_database_url()


def _preflight_test_database(url: str) -> None:
    """Fail fast (seconds, not ~18 minutes of per-test fixture errors) when the
    test database is unreachable, and refuse to run the session's final
    `alembic downgrade base` against a database that is not clearly a test DB."""
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    if "test" not in (parsed.database or "") and os.environ.get("ALLOW_NON_TEST_DATABASE") != "1":
        pytest.exit(
            f"Refusing to run integration tests against database {parsed.database!r}: the session "
            "downgrades the schema to base afterwards. Use a database whose name contains 'test'.",
            returncode=2,
        )
    try:
        probe = create_engine(url, future=True, connect_args={"connect_timeout": 5})
        with probe.connect():
            pass
        probe.dispose()
    except Exception as exc:  # noqa: BLE001 - any connection failure is fatal here
        pytest.exit(
            f"Integration test database unreachable at {parsed.host}:{parsed.port}/{parsed.database} "
            f"({type(exc).__name__}). Start Postgres (infra/docker-compose.yml) or set TEST_DATABASE_URL "
            "(or TEST_DB_HOST/TEST_DB_PORT/TEST_DB_USER/TEST_DB_PASSWORD/TEST_DB_NAME).",
            returncode=2,
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


@event.listens_for(Plan, "before_insert")
def _default_plan_suite(mapper, connection, target):
    """Legacy fixtures predate the Suite->Plan hierarchy (migration 0061 made
    plans.suite_id NOT NULL) and build Plan(...) with no suite. Mirror
    plan_service._resolve_or_validate_suite_id's default (DRONE_UAV, then
    AIRCRAFT) so they keep working; tests that care about suites pass
    suite_id explicitly, which this never overrides."""
    if target.suite_id is not None:
        return
    for code in ("DRONE_UAV", "AIRCRAFT"):
        suite_id = connection.execute(
            select(ProductSuite.id).where(ProductSuite.code == code)
        ).scalar_one_or_none()
        if suite_id is not None:
            target.suite_id = suite_id
            return


@pytest.fixture(scope="session")
def engine():
    _preflight_test_database(TEST_DATABASE_URL)
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
    from tests.support import tokens as _tokens

    _tokens.set_session(session)
    yield session
    _tokens.set_session(None)
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


def grant_features(db_session, organization_id, *feature_keys: str, suite_code: str | None = None) -> None:
    """Give an org an ACTIVE subscription whose plan enables `feature_keys`.

    Routers gated by require_feature (hums, digital_twin, mro_intelligence,
    ...) need a commercial entitlement in addition to RBAC; fixtures that
    build organizations by hand (no /auth/register-organization default plan)
    call this. Uses the default suite via the Plan before_insert hook above.
    """
    from datetime import UTC, datetime, timedelta

    from app.models.plan import PlanFeature
    from app.models.product_catalog import ProductSuite
    from app.models.subscription import Subscription, SubscriptionStatus

    if suite_code is None:
        if "drone_fleet_management" in feature_keys and "aircraft_fleet_management" not in feature_keys:
            target_suite = "DRONE_UAV"
        else:
            target_suite = "AIRCRAFT"
    else:
        target_suite = suite_code

    suite = db_session.execute(
        select(ProductSuite).where(ProductSuite.code == target_suite)
    ).scalar_one_or_none()
    suite_id = suite.id if suite else None

    plan = Plan(
        name=f"Grant-{uuid.uuid4().hex[:8]}",
        code=f"grant-{uuid.uuid4().hex[:12]}",
        suite_id=suite_id,
        is_active=True,
    )
    db_session.add(plan)
    db_session.flush()
    for key in feature_keys:
        db_session.add(PlanFeature(plan_id=plan.id, feature_key=key, enabled=True))
    db_session.add(
        Subscription(
            organization_id=organization_id,
            plan_id=plan.id,
            suite_id=plan.suite_id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.commit()
