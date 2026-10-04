"""Unit tests for edge device provisioning, atomic config writes, and secret masking."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.provision_edge_device import (
    atomic_write_json,
    main,
    mask_secret,
)


def test_mask_secret():
    """Verify secrets are masked in logs and output strings."""
    token = "kdev.1809a043-8e09-48b5-8963-d484a20e6557.supersecretkey999"
    masked = mask_secret(token)
    assert "supersecretkey999" not in masked
    assert masked == "kdev.1809a043-8e09-48b5-8963-d484a20e6557.***"

    # Embedded in an error message
    err_msg = f"HTTP 401: Invalid token {token} presented"
    clean_err = mask_secret(err_msg)
    assert "supersecretkey999" not in clean_err
    assert "kdev.1809a043-8e09-48b5-8963-d484a20e6557.***" in clean_err


def test_atomic_write_json_creates_file(tmp_path):
    """Test atomic write creates destination file with correct contents."""
    target = tmp_path / "subdir" / "gateway.json"
    data = {"device_id": "test-dev-01", "api_url": "https://api.test.com"}

    atomic_write_json(target, data)
    assert target.is_file()

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded == data

    # Verify POSIX file permissions (0600)
    if os.name != "nt":
        stat = target.stat()
        mode = oct(stat.st_mode)[-3:]
        assert mode == "600"


def test_atomic_write_json_refuses_overwrite_without_force(tmp_path):
    """Test atomic write refuses to overwrite existing file unless force=True."""
    target = tmp_path / "gateway.json"
    target.write_text("existing content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        atomic_write_json(target, {"new": "data"}, force=False)

    assert target.read_text(encoding="utf-8") == "existing content"

    # Overwrite succeeds with force=True
    atomic_write_json(target, {"new": "data"}, force=True)
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": "data"}


def test_provision_cli_refuses_overwrite_without_force(tmp_path, caplog):
    """Test CLI returns exit code 1 if destination exists without --force."""
    target = tmp_path / "gateway.json"
    target.write_text("{}", encoding="utf-8")

    code = main([
        "--device-id", "comp-01",
        "--auth-token", "operator-jwt",
        "--output", str(target),
    ])
    assert code == 1
    assert any("Refusing to overwrite existing file" in record.message for record in caplog.records)


def test_provision_cli_requires_auth(tmp_path, caplog):
    """Test CLI returns exit code 1 if no auth token or DB url is provided."""
    target = tmp_path / "gateway.json"

    code = main([
        "--device-id", "comp-01",
        "--output", str(target),
    ])
    assert code == 1
    assert any("Operator authorization required" in record.message for record in caplog.records)


@patch("scripts.provision_edge_device.enroll_via_api")
def test_provision_cli_success(mock_enroll, tmp_path, caplog):
    """Test CLI happy path writes gateway.json with masked logs."""
    target = tmp_path / "gateway.json"
    mock_enroll.return_value = {
        "device_id": "companion-alpha-01",
        "provisioning_token": "kdev.33333333-3333-3333-3333-333333333333.supersecrettoken",
        "status": "ACTIVE",
    }

    with caplog.at_level(logging.INFO):
        code = main([
            "--device-id", "companion-alpha-01",
            "--auth-token", "valid-operator-jwt",
            "--api-url", "https://api.staging.kota.com/api/v1",
            "--mavlink-source", "udp:192.168.1.100:14550",
            "--output", str(target),
        ])
    assert code == 0
    assert target.is_file()

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["device_id"] == "companion-alpha-01"
    assert loaded["device_key"] == "kdev.33333333-3333-3333-3333-333333333333.supersecrettoken"
    assert loaded["mavlink_source"] == "udp:192.168.1.100:14550"
    assert loaded["api_url"] == "https://api.staging.kota.com/api/v1"

    # Verify secret is masked in logs
    expected_mask = "kdev.33333333-3333-3333-3333-333333333333.***"
    assert any(expected_mask in record.message for record in caplog.records)
    assert not any("supersecrettoken" in record.message for record in caplog.records)
