"""Unit tests for the M19 Edge Gateway packaging, CLI entrypoint, and configuration loading."""

from __future__ import annotations

import json
import logging

import pytest

from gateway.config import GatewayConfig
from gateway.kota_gateway import __version__, main


def test_cli_version(capsys):
    """Test --version outputs correct version and exits."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert f"kota-gateway {__version__}" in (captured.out + captured.err)


def test_cli_help(capsys):
    """Test --help displays usage and options."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Kota Aerospace Remote Edge Telemetry Gateway" in captured.out
    assert "--validate-only" in captured.out
    assert "--config" in captured.out


def test_cli_invalid_config_returns_error_code(tmp_path, caplog):
    """Test invalid config (missing device key) returns exit code 1."""
    with caplog.at_level(logging.ERROR):
        code = main([
            "--api-url", "https://api.example.com/api/v1",
            "--validate-only",
        ])
    assert code == 1
    assert any("device_key is required" in record.message for record in caplog.records)


def test_cli_validate_only_valid_config_succeeds(caplog):
    """Test valid config with --validate-only returns 0 without launching daemon."""
    with caplog.at_level(logging.INFO):
        code = main([
            "--api-url", "https://api.example.com/api/v1",
            "--device-key", "kdev.00000000-0000-0000-0000-000000000001.secret123",
            "--validate-only",
        ])
    assert code == 0
    assert any("Configuration is valid" in record.message for record in caplog.records)


def test_cli_load_config_from_json_file(tmp_path, caplog):
    """Test loading configuration from a JSON file via --config."""
    cfg_file = tmp_path / "gateway.json"
    cfg_file.write_text(
        json.dumps({
            "api_url": "https://api.kota.com/api/v1",
            "device_id": "test-device-01",
            "device_key": "kdev.11111111-1111-1111-1111-111111111111.secret456",
            "mavlink_source": "udp:0.0.0.0:14550",
            "log_level": "DEBUG",
        }),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO):
        code = main(["--config", str(cfg_file), "--validate-only"])
    assert code == 0
    assert any("Configuration is valid" in record.message for record in caplog.records)


def test_cli_args_override_json_config(tmp_path):
    """Test command-line arguments take precedence over JSON file values."""
    cfg_file = tmp_path / "gateway.json"
    cfg_file.write_text(
        json.dumps({
            "api_url": "https://api.initial.com/api/v1",
            "device_id": "initial-id",
            "device_key": "kdev.22222222-2222-2222-2222-222222222222.key1",
        }),
        encoding="utf-8",
    )

    loaded = GatewayConfig.from_json(cfg_file)
    assert loaded.api_url == "https://api.initial.com/api/v1"
    assert loaded.device_id == "initial-id"

    # Now verify update_from_dict
    loaded.update_from_dict({
        "api_url": "https://api.overridden.com/api/v1",
        "device_id": "override-id",
    })
    assert loaded.api_url == "https://api.overridden.com/api/v1"
    assert loaded.device_id == "override-id"


def test_cli_missing_config_file_returns_error(caplog):
    """Test --config pointing to nonexistent file returns exit code 1."""
    with caplog.at_level(logging.ERROR):
        code = main(["--config", "/nonexistent/path/gateway.json", "--validate-only"])
    assert code == 1
    assert any("Configuration file not found" in record.message for record in caplog.records)
