"""Regression test for the CI bug in GitHub Actions run 33251440840.

alembic/env.py previously executed:
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
unconditionally, which silently discarded a URL a caller had already set on
the Config object (e.g. a test fixture pointing at a separate test database).
The practical symptom was every integration test failing with
`FATAL: database "aerocomply" does not exist`, because migrations meant for
`aerocomply_test` (set explicitly via alembic_cfg.set_main_option in
conftest.py) were overwritten with the app's default DATABASE_URL.

This test proves the fix holds: it points the *application's* default
DATABASE_URL at a database that does not exist, while explicitly configuring
Alembic with the real TEST_DATABASE_URL, and confirms the migration succeeds
against the explicit URL rather than attempting (and failing) to connect to
the bogus default. If env.py regresses to unconditionally overwriting the
explicit URL, this test fails with the same OperationalError the original
bug produced.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from tests.integration.conftest import TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parents[2]

BOGUS_DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/"
    "aerocomply_this_database_must_never_be_created"
)


def test_explicit_alembic_url_is_not_overwritten_by_app_default(monkeypatch):
    # Simulate the app's default DATABASE_URL pointing at a database that does
    # not exist — exactly the shape of the original bug, where env.py fell
    # back to (or, in the regression case, always used) this value instead of
    # the explicitly configured one.
    monkeypatch.setenv("DATABASE_URL", BOGUS_DEFAULT_DATABASE_URL)
    get_settings.cache_clear()
    try:
        assert get_settings().database_url == BOGUS_DEFAULT_DATABASE_URL

        alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
        alembic_cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))

        # If env.py ever regresses to unconditionally overwriting this with
        # get_settings().database_url, this raises the same
        # sqlalchemy.exc.OperationalError ("database ... does not exist")
        # that caused every integration test to fail in CI run 33251440840.
        command.upgrade(alembic_cfg, "head")
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()
