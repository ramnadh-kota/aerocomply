"""Gateway health and operational diagnostics matching EdgeDeviceHeartbeatRequest."""

from __future__ import annotations

import os
import platform
import time
from datetime import UTC, datetime
from typing import Any


def get_gateway_health_payload(
    device_id: str,
    queue_stats: dict[str, Any] | None = None,
    *,
    start_time: float | None = None,
    software_version: str = "1.0.0",
    firmware_version: str | None = None,
    connectivity_state: str = "ONLINE",
    sensor_states: dict[str, str] | None = None,
    config_version: int = 1,
    extra_observability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate canonical heartbeat payload matching backend EdgeDeviceHeartbeatRequest.

    Backend schema (EdgeDeviceHeartbeatRequest):
        device_id: str
        timestamp: datetime (ISO-8601 string)
        firmware_version: str | None
        software_version: str | None
        uptime_seconds: int | None
        connectivity_state: str | None ("ONLINE" | "DEGRADED" | "CELLULAR_BACKUP")
        sensor_states: dict[str, str] | None
        queue_depth: int | None
        config_version: int | None
        observability: dict[str, Any] | None
    """
    stats = queue_stats or {}

    load_avg = 0.0
    if hasattr(os, "getloadavg"):
        try:
            load_avg = os.getloadavg()[0]
        except Exception:
            pass

    uptime_sec: int | None = None
    if start_time is not None:
        uptime_sec = max(0, int(time.time() - start_time))

    pending_items = int(stats.get("pending_items", 0))

    observability: dict[str, Any] = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "load_1min": load_avg,
        "queue_metrics": {
            "total_items": stats.get("total_items", 0),
            "total_bytes": stats.get("total_bytes", 0),
            "pending_items": pending_items,
            "in_flight_items": stats.get("in_flight_items", 0),
            "quarantined_items": stats.get("quarantined_items", 0),
        },
    }
    if extra_observability:
        observability.update(extra_observability)

    return {
        "device_id": device_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "connectivity_state": connectivity_state,
        "queue_depth": pending_items,
        "software_version": software_version,
        "firmware_version": firmware_version,
        "uptime_seconds": uptime_sec,
        "sensor_states": sensor_states or {},
        "config_version": config_version,
        "observability": observability,
    }
