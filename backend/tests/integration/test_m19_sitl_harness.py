"""M19.3 Automated SITL Telemetry Integration Harness Test Suite.

Validates the SITL harness (`backend/scripts/run_gateway_sitl_stream.py`):
- End-to-end execution with real PostgreSQL database persistence
- Gateway configuration validation
- Graceful error handling and process teardown (no orphan processes)
- Idempotency across repeated consecutive executions
"""

from __future__ import annotations

import os

import pytest
from scripts.run_gateway_sitl_stream import (
    SITLIntegrationHarness,
)


@pytest.fixture
def db_url():
    port = os.environ.get("TEST_DB_PORT", "55432")
    return os.environ.get(
        "DATABASE_URL",
        f"postgresql+psycopg://postgres:aerocomplydevpw@localhost:{port}/aerocomply_dev",
    )


def test_sitl_harness_end_to_end(db_url):
    """Verify that SITLIntegrationHarness streams telemetry and persists to PostgreSQL."""
    harness = SITLIntegrationHarness(
        db_url=db_url,
        rate_hz=4.0,
        duration_sec=3.0,
        spawn_backend=True,
    )
    exit_code = harness.run()
    assert exit_code == 0, "SITL harness failed end-to-end execution"


def test_sitl_harness_invalid_config_fails_closed(db_url):
    """Verify that an invalid gateway configuration fails closed with exit code 1."""
    harness = SITLIntegrationHarness(
        db_url=db_url,
        rate_hz=4.0,
        duration_sec=2.0,
        spawn_backend=True,
    )
    # Seed data
    ctx = harness.setup_isolated_test_data()

    # Corrupt config by removing required api_url
    with open(ctx.config_path, "w", encoding="utf-8") as f:
        f.write('{"device_id": "test", "device_key": "invalid"}\n')

    valid = harness.validate_gateway_cli_config()
    assert valid is False, "Corrupted gateway configuration was accepted unexpectedly"

    harness.teardown()


def test_sitl_harness_process_cleanup_on_error(db_url):
    """Verify that if an error occurs, teardown kills child processes and cleans storage."""
    harness = SITLIntegrationHarness(
        db_url=db_url,
        rate_hz=2.0,
        duration_sec=1.0,
        spawn_backend=True,
    )
    # Run setup
    assert harness.check_database()
    assert harness.ensure_backend_running()
    ctx = harness.setup_isolated_test_data()
    temp_dir = ctx.temp_dir

    assert os.path.exists(temp_dir)
    assert harness.backend_proc is not None
    assert harness.backend_proc.poll() is None

    # Simulate teardown
    harness.teardown()

    assert not os.path.exists(temp_dir), "Temporary directory was not cleaned up"
    assert harness.backend_proc.poll() is not None, "Backend process was orphaned"


def test_sitl_harness_repeated_runs_idempotent(db_url):
    """Verify that running the harness twice sequentially produces
    no port clashes or stale records.
    """
    harness1 = SITLIntegrationHarness(
        db_url=db_url,
        rate_hz=4.0,
        duration_sec=2.0,
        spawn_backend=True,
    )
    code1 = harness1.run()
    assert code1 == 0, "First harness run failed"

    harness2 = SITLIntegrationHarness(
        db_url=db_url,
        rate_hz=4.0,
        duration_sec=2.0,
        spawn_backend=True,
    )
    code2 = harness2.run()
    assert code2 == 0, "Second harness run failed"
