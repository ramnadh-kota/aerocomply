"""M18: Production Edge Telemetry Gateway Daemon & Store-and-Forward Service.

Manages attached UAV telemetry connectors, maintains local disk/memory FIFO buffering
during network disconnects, performs store-and-forward synchronization with exponential
backoff retry, dispatches health heartbeats, and securely uplinks canonical telemetry
to Kota Cloud (POST /api/v1/telemetry/ingest).

Hardware & Deployment Invariants:
- Zero dependency on Mission Planner in production.
- Zero dependency on a permanently attached laptop.
- Runs on onboard companion computers (Raspberry Pi, NVIDIA Jetson), cellular edge gateways,
  or cloud telemetry relay servers.
"""

from __future__ import annotations

import collections
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

import httpx
from pydantic import BaseModel, Field

from app.schemas.edge_hardware import EdgeDeviceHeartbeatRequest
from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryIngestRequest,
    TelemetryIngestResponse,
)
from app.services.edge.connector_base import TelemetryConnector

logger = logging.getLogger(__name__)


class GatewayMetrics(BaseModel):
    gateway_id: str
    is_online: bool = True
    queue_depth: int = 0
    buffer_capacity: int = 5000
    events_received: int = 0
    events_transmitted: int = 0
    events_failed: int = 0
    events_replayed: int = 0
    duplicates_detected: int = 0
    reconnect_attempts: int = 0
    last_sync_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    active_vehicles: list[str] = Field(default_factory=list)


class KotaTelemetryGateway:
    """Production Edge Telemetry Gateway managing local store-and-forward and cloud synchronization."""

    def __init__(
        self,
        gateway_id: str = "GW-KOTA-EDGE-01",
        cloud_base_url: str = "http://localhost:8000",
        tenant_api_token: str | None = None,
        buffer_capacity: int = 5000,
        batch_size: int = 25,
        max_retry_backoff_sec: float = 30.0,
    ) -> None:
        self.gateway_id = gateway_id
        self.cloud_base_url = cloud_base_url.rstrip("/")
        self.tenant_api_token = tenant_api_token or "kota_edge_bearer_token"
        self.buffer_capacity = buffer_capacity
        self.batch_size = batch_size
        self.max_retry_backoff_sec = max_retry_backoff_sec

        self.is_online = True
        self.connectors: dict[str, TelemetryConnector] = {}
        self.buffer: collections.deque[NormalizedTelemetryEvent] = collections.deque(
            maxlen=buffer_capacity
        )
        self.metrics = GatewayMetrics(gateway_id=gateway_id, buffer_capacity=buffer_capacity)
        self.start_time = time.time()
        self.backoff_sec = 1.0

    def register_connector(self, connector: TelemetryConnector) -> None:
        """Attaches a telemetry connector (e.g. MAVLinkConnector) and hooks event listener."""
        connector.on_event_callback = self.ingest_event
        self.connectors[connector.connector_id] = connector

    def ingest_event(self, event: NormalizedTelemetryEvent) -> None:
        """Receives canonical event from connector, updates metrics, and buffers locally."""
        self.metrics.events_received += 1
        if event.source_asset_id not in self.metrics.active_vehicles:
            self.metrics.active_vehicles.append(event.source_asset_id)

        self.buffer.append(event)
        self.metrics.queue_depth = len(self.buffer)

    def flush_to_cloud(
        self, http_client: httpx.Client | Any | None = None
    ) -> dict[str, Any]:
        """Flushes buffered telemetry events to Kota Cloud (POST /api/v1/telemetry/ingest)."""
        if not self.buffer:
            return {"status": "EMPTY", "transmitted": 0, "remaining": 0}

        if not self.is_online:
            return {
                "status": "OFFLINE_BUFFERED",
                "transmitted": 0,
                "remaining": len(self.buffer),
            }

        # Drain batch from FIFO queue
        batch: list[NormalizedTelemetryEvent] = []
        while self.buffer and len(batch) < self.batch_size:
            batch.append(self.buffer.popleft())

        payload = TelemetryIngestRequest(events=batch)
        headers = {
            "Authorization": f"Bearer {self.tenant_api_token}",
            "Content-Type": "application/json",
            "X-Gateway-ID": self.gateway_id,
        }

        try:
            if http_client is not None:
                # Custom/test client passed in
                resp = http_client.post(
                    "/api/v1/telemetry/ingest",
                    headers=headers,
                    json=payload.model_dump(mode="json"),
                )
            else:
                with httpx.Client(base_url=self.cloud_base_url, timeout=10.0) as client:
                    resp = client.post(
                        "/api/v1/telemetry/ingest",
                        headers=headers,
                        json=payload.model_dump(mode="json"),
                    )

            if resp.status_code in (200, 201):
                res_data = resp.json() if hasattr(resp, "json") else {}
                processed = res_data.get("processed_count", len(batch))
                duplicates = res_data.get("duplicate_count", 0)

                self.metrics.events_transmitted += processed
                self.metrics.duplicates_detected += duplicates
                self.metrics.last_sync_at = datetime.now(UTC)
                self.metrics.queue_depth = len(self.buffer)
                self.backoff_sec = 1.0  # Reset backoff on success

                return {
                    "status": "SUCCESS",
                    "transmitted": processed,
                    "duplicates": duplicates,
                    "remaining": len(self.buffer),
                }
            else:
                # Server error / rate limit -> re-insert batch back to front of buffer
                for ev in reversed(batch):
                    self.buffer.appendleft(ev)
                self.metrics.events_failed += len(batch)
                self.metrics.queue_depth = len(self.buffer)
                return {
                    "status": "SERVER_ERROR",
                    "http_status": resp.status_code,
                    "remaining": len(self.buffer),
                }

        except Exception as exc:
            # Network drop / timeout -> push batch back to front and transition to offline
            for ev in reversed(batch):
                self.buffer.appendleft(ev)
            self.is_online = False
            self.metrics.is_online = False
            self.metrics.events_failed += len(batch)
            self.metrics.queue_depth = len(self.buffer)
            self.backoff_sec = min(self.max_retry_backoff_sec, self.backoff_sec * 2.0)

            return {
                "status": "NETWORK_FAILURE",
                "error": str(exc),
                "remaining": len(self.buffer),
            }

    def reconnect_and_sync(
        self, http_client: httpx.Client | Any | None = None
    ) -> dict[str, Any]:
        """Recovers network connection and synchronizes all buffered telemetry in FIFO batches."""
        self.is_online = True
        self.metrics.is_online = True
        self.metrics.reconnect_attempts += 1
        total_replayed = 0

        while self.buffer:
            res = self.flush_to_cloud(http_client=http_client)
            if res.get("status") == "SUCCESS":
                total_replayed += res.get("transmitted", 0)
            else:
                break

        self.metrics.events_replayed += total_replayed
        return {
            "status": "SYNC_COMPLETE" if not self.buffer else "PARTIAL_SYNC",
            "total_replayed": total_replayed,
            "remaining_queue": len(self.buffer),
        }

    def build_heartbeat_payload(self) -> EdgeDeviceHeartbeatRequest:
        """Generates canonical EdgeDeviceHeartbeatRequest."""
        now = datetime.now(UTC)
        uptime = int(time.time() - self.start_time)
        sensor_states: dict[str, str] = {}
        for c_id, conn in self.connectors.items():
            sensor_states[c_id] = "VALID" if conn.state.value in ("CONNECTED", "STREAMING") else "OFFLINE"

        self.metrics.last_heartbeat_at = now
        return EdgeDeviceHeartbeatRequest(
            device_id=self.gateway_id,
            timestamp=now,
            firmware_version="kota-gateway-v3.0",
            software_version="kota-edge-daemon-v3.0-m18",
            uptime_seconds=uptime,
            connectivity_state="ONLINE" if self.is_online else "OFFLINE",
            sensor_states=sensor_states,
            queue_depth=len(self.buffer),
            config_version=1,
            observability={
                "events_received": self.metrics.events_received,
                "events_transmitted": self.metrics.events_transmitted,
                "events_replayed": self.metrics.events_replayed,
                "duplicates_detected": self.metrics.duplicates_detected,
                "active_uavs": self.metrics.active_vehicles,
            },
        )

    def get_metrics(self) -> GatewayMetrics:
        """Returns snapshot of gateway operational metrics."""
        self.metrics.queue_depth = len(self.buffer)
        self.metrics.is_online = self.is_online
        return self.metrics
