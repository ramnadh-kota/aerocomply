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
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.deps import get_db_session
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test",
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


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
