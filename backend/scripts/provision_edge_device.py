"""Kota Aerospace — Secure Edge Device Provisioning CLI.

Enrolls an edge companion computer through the authorized backend device provisioning
workflow, generates or retrieves HMAC machine credentials, and writes a secured (0600)
gateway configuration file without printing secrets to logs or terminal.

Usage via API (preferred for remote companion computers):
    python scripts/provision_edge_device.py \\
        --api-url https://api.aerocomply.com/api/v1 \\
        --auth-token "<OPERATOR_JWT>" \\
        --device-id companion-cm4-01 \\
        --output /etc/kota/gateway.json

Usage via Direct Database (for backend operators / initial deployment):
    DATABASE_URL=postgresql+psycopg://... \\
        python scripts/provision_edge_device.py \\
        --org-id <ORGANIZATION_UUID> \\
        --device-id companion-cm4-01 \\
        --output /etc/kota/gateway.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("provision_edge_device")

_SECRET_PATTERN = re.compile(r"kdev\.[0-9a-fA-F-]+\.[A-Za-z0-9_-]+")


def mask_secret(text: str) -> str:
    """Mask sensitive device tokens in messages and logs."""
    def _mask_match(m: re.Match[str]) -> str:
        parts = m.group(0).split(".")
        if len(parts) == 3:
            return f"{parts[0]}.{parts[1]}.***"
        return "kdev.***"

    return _SECRET_PATTERN.sub(_mask_match, str(text))


def atomic_write_json(target_path: Path, data: dict[str, Any], *, force: bool = False) -> None:
    """Safely write JSON configuration to target_path with restricted 0600 permissions."""
    if target_path.exists() and not force:
        raise FileExistsError(
            f"Target configuration file already exists: {target_path}. "
            "Use --force to overwrite."
        )

    parent_dir = target_path.parent
    parent_dir.mkdir(parents=True, exist_ok=True)

    # Write to a secure temporary file in the same filesystem directory for atomic rename
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        dir=parent_dir,
        prefix=f".{target_path.name}.tmp_",
        text=True,
    )
    tmp_path = Path(tmp_path_str)

    try:
        # Enforce restricted permissions (0600: read/write only by owner) on POSIX
        if os.name != "nt":
            os.chmod(tmp_path, 0o600)

        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

        # Atomic replacement guarantees no half-written files
        os.replace(tmp_path, target_path)

        # Ensure permissions on target file after replacement
        if os.name != "nt":
            os.chmod(target_path, 0o600)

    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise


def enroll_via_api(
    api_url: str,
    auth_token: str,
    device_id: str,
    device_type: str = "EDGE_GATEWAY",
    asset_id: str | None = None,
) -> dict[str, Any]:
    """Enroll edge device using backend REST API (/api/v1/edge/devices/provision)."""
    endpoint = f"{api_url.rstrip('/')}/edge/devices/provision"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}",
        "User-Agent": "Kota-Device-Provisioner/1.0",
    }
    payload: dict[str, Any] = {
        "device_id": device_id,
        "device_type": device_type,
    }
    if asset_id:
        payload["asset_id"] = asset_id

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="ignore")
        clean_err = mask_secret(err_msg)
        raise RuntimeError(
            f"Backend enrollment failed (HTTP {exc.code} {exc.reason}): {clean_err}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Network error communicating with backend API: {exc}") from exc


def enroll_via_database(
    database_url: str,
    organization_id: uuid.UUID,
    device_id: str,
    device_type: str = "EDGE_GATEWAY",
    asset_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Enroll edge device directly via database session (operator bootstrap mode)."""
    # Dynamic import to avoid backend database dependencies on companion computers
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.schemas.edge_hardware import EdgeDeviceProvisionRequest
    from app.services import edge_hardware_service

    engine = create_engine(database_url)
    with Session(engine) as db:
        payload = EdgeDeviceProvisionRequest(
            device_id=device_id,
            device_type=device_type,
            asset_id=asset_id,
        )
        resp = edge_hardware_service.provision_edge_device(
            db,
            organization_id=organization_id,
            payload=payload,
            actor_user_id=actor_user_id,
        )
        db.commit()
        return resp.model_dump()


def verify_device_heartbeat(api_url: str, device_id: str, device_token: str) -> bool:
    """Perform initial diagnostic heartbeat validation with newly minted credentials."""
    from datetime import UTC, datetime

    endpoint = f"{api_url.rstrip('/')}/device/heartbeat"
    headers = {
        "Content-Type": "application/json",
        "X-Kota-Device-Key": device_token,
        "User-Agent": "Kota-Device-Provisioner/1.0",
    }
    payload = {
        "device_id": device_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "connectivity_state": "ONLINE",
        "queue_depth": 0,
        "software_version": "1.0.0",
        "observability": {"provisioning_check": True},
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status == 200
    except Exception as exc:
        clean_err = mask_secret(str(exc))
        logger.warning(f"Initial heartbeat verification failed: {clean_err}")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="provision_edge_device",
        description="Kota Aerospace Secure Edge Companion Computer Provisioning",
    )
    parser.add_argument(
        "--device-id",
        required=True,
        help="Unique edge device identifier (e.g. companion-01)",
    )
    parser.add_argument(
        "--device-type",
        default="EDGE_GATEWAY",
        choices=["EDGE_GATEWAY", "MAVLINK_TELEMETRY", "ONBOARD_SENSOR"],
        help="Device hardware category (default: EDGE_GATEWAY)",
    )
    parser.add_argument(
        "--asset-id",
        default=None,
        help="Optional UUID of assigned aircraft or UAS",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="/etc/kota/gateway.json",
        help="Target configuration file destination (default: /etc/kota/gateway.json)",
    )
    parser.add_argument(
        "--api-url",
        default=os.environ.get("KOTA_API_URL", "https://api.aerocomply.com/api/v1"),
        help="Target Kota Aerospace platform API endpoint URL",
    )
    parser.add_argument(
        "--auth-token",
        default=os.environ.get("KOTA_AUTH_TOKEN"),
        help="Operator/admin JWT bearer token with ORG_MANAGE permission",
    )
    parser.add_argument(
        "--org-id",
        default=os.environ.get("KOTA_ORG_ID"),
        help="Organization UUID (required only for direct database mode)",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Direct database connection URL (optional local bootstrap mode)",
    )
    parser.add_argument(
        "--mavlink-source",
        default="udp:127.0.0.1:14550",
        help="Ingress MAVLink source URL for gateway.json (default: udp:127.0.0.1:14550)",
    )
    parser.add_argument(
        "--queue-db-path",
        default="/var/lib/kota/gateway_queue.db",
        help="SQLite queue database path (default: /var/lib/kota/gateway_queue.db)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        default=False,
        help="Overwrite existing configuration file without confirmation",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=False,
        help="Perform immediate authenticated heartbeat handshake against API to verify token",
    )

    args = parser.parse_args(argv)
    target_path = Path(args.output).resolve()

    # Step 1: Check existing destination
    if target_path.exists() and not args.force:
        logger.error(
            f"Refusing to overwrite existing file '{target_path}'. "
            "Use --force to overwrite."
        )
        return 1

    # Step 2: Enroll device
    result: dict[str, Any]
    try:
        if args.auth_token:
            logger.info(f"Enrolling device '{args.device_id}' via API endpoint: {args.api_url}")
            result = enroll_via_api(
                api_url=args.api_url,
                auth_token=args.auth_token,
                device_id=args.device_id,
                device_type=args.device_type,
                asset_id=args.asset_id,
            )
        elif args.database_url and args.org_id:
            logger.info(f"Enrolling device '{args.device_id}' directly via database")
            result = enroll_via_database(
                database_url=args.database_url,
                organization_id=uuid.UUID(args.org_id),
                device_id=args.device_id,
                device_type=args.device_type,
                asset_id=uuid.UUID(args.asset_id) if args.asset_id else None,
            )
        else:
            logger.error(
                "Operator authorization required. Provide --auth-token (or KOTA_AUTH_TOKEN), "
                "or --database-url with --org-id for direct database enrollment."
            )
            return 1
    except Exception as exc:
        clean_err = mask_secret(str(exc))
        logger.error(f"Enrollment failure: {clean_err}")
        return 2

    token = result.get("provisioning_token")
    if not token or not token.startswith("kdev."):
        logger.error("Enrollment failed: backend did not return a valid 'kdev' device token.")
        return 2

    masked_token = mask_secret(token)
    logger.info(
        f"Device enrolled successfully (Device ID: {args.device_id}, Token: {masked_token})"
    )

    # Step 3: Verify initial connectivity if requested
    if args.verify:
        logger.info("Executing initial diagnostic heartbeat handshake...")
        if verify_device_heartbeat(args.api_url, args.device_id, token):
            logger.info("Heartbeat verification passed: credentials authenticated and active.")
        else:
            logger.warning("Heartbeat verification failed. Check API URL and tenant entitlements.")

    # Step 4: Write configuration safely
    config_data = {
        "api_url": args.api_url.rstrip("/"),
        "device_id": args.device_id,
        "device_key": token,
        "mavlink_source": args.mavlink_source,
        "queue_db_path": args.queue_db_path,
        "allow_insecure_http": False,
        "heartbeat_interval_seconds": 15.0,
        "batch_size_bytes": 65536,
        "max_queue_entries": 50000,
        "max_queue_bytes": 104857600,
        "log_level": "INFO",
    }

    try:
        atomic_write_json(target_path, config_data, force=args.force)
        logger.info(f"Secure configuration written atomically to '{target_path}' (mode 0600).")
        logger.info("Provisioning completed successfully.")
        return 0
    except Exception as exc:
        logger.error(f"Failed to write configuration file: {exc}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
