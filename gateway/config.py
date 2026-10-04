"""Configuration management for the Kota Remote Edge Gateway."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("kota_gateway.config")


@dataclass
class GatewayConfig:
    """Validated configuration for the edge telemetry gateway."""

    api_url: str = "https://localhost:8001/api/v1"
    device_id: str = ""
    device_key: str = ""
    credential_file: str = ""
    allow_insecure_http: bool = False
    mavlink_source: str = "udp:127.0.0.1:14550"
    baud_rate: int = 57600
    queue_db_path: str = "./gateway_queue.db"
    batch_size_bytes: int = 65536  # 64 KB default upload batch
    batch_timeout_seconds: float = 0.5  # Flush batch at least every 500ms
    max_queue_entries: int = 50000
    max_queue_bytes: int = 100 * 1024 * 1024  # 100 MB
    heartbeat_interval_seconds: float = 15.0
    request_timeout_seconds: float = 10.0
    max_backoff_seconds: float = 30.0
    base_backoff_seconds: float = 0.5
    enable_tls_verify: bool = True
    min_tls_version: str = "TLSv1_2"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> GatewayConfig:
        """Load configuration from environment variables."""
        e = env if env is not None else os.environ
        cfg = cls(
            api_url=e.get("KOTA_API_URL", "https://localhost:8001/api/v1").rstrip("/"),
            device_id=e.get("KOTA_DEVICE_ID", ""),
            device_key=e.get("KOTA_DEVICE_KEY", ""),
            credential_file=e.get("KOTA_CREDENTIAL_FILE", ""),
            allow_insecure_http=e.get("KOTA_ALLOW_INSECURE_HTTP", "false").lower() in ("true", "1", "yes"),
            mavlink_source=e.get("KOTA_MAVLINK_SOURCE", "udp:127.0.0.1:14550"),
            baud_rate=int(e.get("KOTA_BAUD_RATE", "57600")),
            queue_db_path=e.get("KOTA_QUEUE_DB_PATH", "./gateway_queue.db"),
            batch_size_bytes=int(e.get("KOTA_BATCH_SIZE_BYTES", "65536")),
            batch_timeout_seconds=float(e.get("KOTA_BATCH_TIMEOUT_SECONDS", "0.5")),
            max_queue_entries=int(e.get("KOTA_MAX_QUEUE_ENTRIES", "50000")),
            max_queue_bytes=int(e.get("KOTA_MAX_QUEUE_BYTES", str(100 * 1024 * 1024))),
            heartbeat_interval_seconds=float(e.get("KOTA_HEARTBEAT_INTERVAL_SECONDS", "15.0")),
            request_timeout_seconds=float(e.get("KOTA_REQUEST_TIMEOUT_SECONDS", "10.0")),
            max_backoff_seconds=float(e.get("KOTA_MAX_BACKOFF_SECONDS", "30.0")),
            base_backoff_seconds=float(e.get("KOTA_BASE_BACKOFF_SECONDS", "0.5")),
            enable_tls_verify=e.get("KOTA_TLS_VERIFY", "true").lower() in ("true", "1", "yes"),
            min_tls_version=e.get("KOTA_MIN_TLS_VERSION", "TLSv1_2"),
            log_level=e.get("KOTA_LOG_LEVEL", "INFO").upper(),
        )
        cfg.load_credential_file()
        return cfg

    @classmethod
    def from_json(cls, json_path: str | Path, env: dict[str, str] | None = None) -> GatewayConfig:
        """Load configuration from a JSON file, with optional env overrides."""
        cfg = cls.from_env(env=env)
        path = Path(json_path)
        if not path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {json_path}")

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Failed to parse JSON configuration file '{json_path}': {exc}") from exc

        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a JSON object, got {type(data).__name__}")

        cfg.update_from_dict(data)
        cfg.load_credential_file()
        return cfg

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """Update configuration fields from a dictionary."""
        for key, val in data.items():
            if hasattr(self, key):
                target_type = type(getattr(self, key))
                if target_type is bool and isinstance(val, str):
                    setattr(self, key, val.lower() in ("true", "1", "yes"))
                elif target_type in (int, float, str, bool):
                    setattr(self, key, target_type(val))
                else:
                    setattr(self, key, val)

    def load_credential_file(self) -> None:
        """Safely load credentials from file if credential_file is set and device_key is empty."""
        if not self.credential_file:
            return

        cred_path = Path(self.credential_file)
        if not cred_path.is_file():
            logger.warning(f"Configured credential file not found: {self.credential_file}")
            return

        try:
            content = cred_path.read_text(encoding="utf-8").strip()
            # Try parsing as JSON first
            if content.startswith("{"):
                data = json.loads(content)
                if not self.device_key and "device_key" in data:
                    self.device_key = str(data["device_key"]).strip()
                if not self.device_id and "device_id" in data:
                    self.device_id = str(data["device_id"]).strip()
            else:
                # Plain text single-line token
                if not self.device_key:
                    self.device_key = content
        except Exception as exc:
            logger.error(f"Failed to read credential file '{self.credential_file}': {exc}")

    def validate(self) -> list[str]:
        """Validate configuration values, returning a list of validation error messages."""
        self.load_credential_file()
        errors: list[str] = []

        if not self.api_url:
            errors.append("api_url cannot be empty")
        elif not (self.api_url.startswith("http://") or self.api_url.startswith("https://")):
            errors.append("api_url must start with http:// or https://")
        elif self.api_url.startswith("http://") and not self.allow_insecure_http:
            errors.append(
                "Insecure HTTP transport rejected. Production requires HTTPS. "
                "For local testing only, enable allow_insecure_http."
            )

        if not self.device_key:
            errors.append("device_key is required (set KOTA_DEVICE_KEY or KOTA_CREDENTIAL_FILE)")
        elif not self.device_key.startswith("kdev."):
            errors.append("device_key format invalid (must start with 'kdev.')")

        if self.batch_size_bytes <= 0 or self.batch_size_bytes > 1024 * 1024:
            errors.append("batch_size_bytes must be between 1 and 1048576 (1MB)")

        if self.max_queue_entries <= 0:
            errors.append("max_queue_entries must be positive")

        if self.min_tls_version not in ("TLSv1_2", "TLSv1_3"):
            errors.append("min_tls_version must be 'TLSv1_2' or 'TLSv1_3'")

        if not self.enable_tls_verify:
            logger.warning("SECURITY WARNING: TLS certificate verification is disabled (enable_tls_verify=False).")

        return errors
