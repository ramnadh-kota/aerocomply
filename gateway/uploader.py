"""HTTP client for transmitting telemetry batches and heartbeats to Kota Cloud with TLS security."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from typing import Any

from gateway.ack_handler import mask_secret
from gateway.config import GatewayConfig

logger = logging.getLogger("kota_gateway.uploader")


class TelemetryUploader:
    """Uploads telemetry batches and health heartbeats to Kota Aerospace cloud endpoints."""

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.mavlink_url = f"{self.config.api_url}/device/telemetry/mavlink"
        self.heartbeat_url = f"{self.config.api_url}/device/heartbeat"

        # Validate transport security
        if self.config.api_url.startswith("http://") and not self.config.allow_insecure_http:
            raise ValueError(
                "Insecure HTTP transport is prohibited. Use HTTPS or set allow_insecure_http=True for local testing."
            )

        # Configure hardened TLS context
        self.ssl_context = ssl.create_default_context()
        if hasattr(ssl, "TLSVersion"):
            min_ver = ssl.TLSVersion.TLSv1_3 if self.config.min_tls_version == "TLSv1_3" else ssl.TLSVersion.TLSv1_2
            self.ssl_context.minimum_version = min_ver

        if not self.config.enable_tls_verify:
            logger.warning("SECURITY WARNING: TLS certificate verification is disabled!")
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    def upload_mavlink_batch(self, raw_bytes: bytes) -> tuple[int, dict[str, Any] | str]:
        """POST raw MAVLink bytes to /api/v1/device/telemetry/mavlink.

        Returns:
            (status_code, response_data_dict_or_str)
        """
        if not raw_bytes:
            return 200, {"accepted": 0, "message": "empty batch"}

        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(raw_bytes)),
            "X-Kota-Device-Key": self.config.device_key,
            "User-Agent": "Kota-Edge-Gateway/1.1",
        }

        req = urllib.request.Request(
            url=self.mavlink_url,
            data=raw_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, context=self.ssl_context, timeout=self.config.request_timeout_seconds
            ) as resp:
                status_code = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")
                try:
                    data = json.loads(body)
                except Exception:
                    data = {"raw": body}
                return status_code, data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                err_data = json.loads(err_body)
            except Exception:
                err_data = {"error": mask_secret(err_body)}
            return e.code, err_data
        except Exception as e:
            clean_err = mask_secret(str(e))
            return 0, {"error": f"Network Error: {clean_err}"}

    def send_heartbeat(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
        """POST JSON heartbeat to /api/v1/device/heartbeat.

        Returns:
            (status_code, response_data_dict_or_str)
        """
        json_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(json_bytes)),
            "X-Kota-Device-Key": self.config.device_key,
            "User-Agent": "Kota-Edge-Gateway/1.1",
        }

        req = urllib.request.Request(
            url=self.heartbeat_url,
            data=json_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, context=self.ssl_context, timeout=self.config.request_timeout_seconds
            ) as resp:
                status_code = resp.getcode()
                body = resp.read().decode("utf-8", errors="ignore")
                try:
                    data = json.loads(body)
                except Exception:
                    data = {"raw": body}
                return status_code, data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            try:
                err_data = json.loads(err_body)
            except Exception:
                err_data = {"error": mask_secret(err_body)}
            return e.code, err_data
        except Exception as e:
            clean_err = mask_secret(str(e))
            return 0, {"error": f"Network Error: {clean_err}"}
