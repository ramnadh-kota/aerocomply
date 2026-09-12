"""Production-safety fail-fast guards in app/main.py: outside a development
environment, the app must refuse to start with either the default
placeholder JWT_SECRET_KEY or the default local-development DATABASE_URL —
silently accepting either would mean a misconfigured production deploy
either signs tokens with a publicly-known secret or quietly tries to reach
a localhost Postgres that doesn't exist.

Runs app.main in a subprocess (not a plain import) because Python caches
module imports within one process — the module-level guard only runs once,
so re-importing in-process after the first test wouldn't re-trigger it.
"""

import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]

_VALID_DATABASE_URL = "postgresql+psycopg://user:pass@example-prod-host:5432/aerocomply_prod"
_VALID_JWT_SECRET = "a-real-production-secret-not-the-placeholder"
_DEFAULT_JWT_SECRET = "CHANGE_ME_IN_PRODUCTION"
_DEFAULT_DATABASE_URL = "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply"


def _run_import(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=str(BACKEND_DIR),
        env=env_overrides,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _base_env(**overrides: str) -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env.pop("JWT_SECRET_KEY", None)
    env.pop("ENVIRONMENT", None)
    env.update(overrides)
    return env


def test_production_environment_rejects_default_jwt_secret():
    result = _run_import(
        _base_env(
            ENVIRONMENT="production",
            DATABASE_URL=_VALID_DATABASE_URL,
            JWT_SECRET_KEY=_DEFAULT_JWT_SECRET,
        )
    )
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr


def test_production_environment_rejects_default_database_url():
    result = _run_import(
        _base_env(
            ENVIRONMENT="production",
            DATABASE_URL=_DEFAULT_DATABASE_URL,
            JWT_SECRET_KEY=_VALID_JWT_SECRET,
        )
    )
    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_production_environment_starts_with_real_config():
    result = _run_import(
        _base_env(
            ENVIRONMENT="production",
            DATABASE_URL=_VALID_DATABASE_URL,
            JWT_SECRET_KEY=_VALID_JWT_SECRET,
        )
    )
    assert result.returncode == 0, result.stderr


def test_development_environment_allows_default_placeholders():
    """The defaults exist specifically so local dev works with zero
    configuration — only non-development environments are guarded."""
    result = _run_import(
        _base_env(
            ENVIRONMENT="development",
            DATABASE_URL=_DEFAULT_DATABASE_URL,
            JWT_SECRET_KEY=_DEFAULT_JWT_SECRET,
        )
    )
    assert result.returncode == 0, result.stderr
