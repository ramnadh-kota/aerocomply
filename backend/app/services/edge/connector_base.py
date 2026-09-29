"""M18: Telemetry Connector Base Abstraction.

Defines the hardware-independent, vendor-neutral interface for all UAV telemetry
protocols (MAVLink, PX4 uORB, DJI SDK, MQTT, REST, WebSocket).

Invariants:
- Connectors handle protocol-level deserialization and unit conversion.
- Connectors produce canonical NormalizedTelemetryEvent objects.
- Connectors do not perform HUMS feature extraction or diagnostic reasoning.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Callable
from pydantic import BaseModel, Field

from app.schemas.telemetry import NormalizedTelemetryEvent


class ConnectorState(str, enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    STREAMING = "STREAMING"
    STALE = "STALE"
    ERROR = "ERROR"


class ConnectorStats(BaseModel):
    connector_id: str
    protocol: str
    state: ConnectorState = ConnectorState.DISCONNECTED
    messages_received: int = 0
    events_generated: int = 0
    bytes_received: int = 0
    parse_errors: int = 0
    last_message_at: datetime | None = None
    connected_at: datetime | None = None
    active_system_ids: list[int] = Field(default_factory=list)


class TelemetryConnector(ABC):
    """Abstract base class for all UAV telemetry ingestion connectors."""

    def __init__(
        self,
        connector_id: str,
        protocol: str = "GENERIC",
        on_event_callback: Callable[[NormalizedTelemetryEvent], Any] | None = None,
    ) -> None:
        self.connector_id = connector_id
        self.protocol = protocol
        self.on_event_callback = on_event_callback
        self.state = ConnectorState.DISCONNECTED
        self.stats = ConnectorStats(connector_id=connector_id, protocol=protocol)

    @abstractmethod
    def connect(self, endpoint_uri: str, **kwargs: Any) -> bool:
        """Establishes connection to the physical or virtual telemetry stream (Serial/UDP/TCP/Stream)."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Terminates telemetry stream connection cleanly."""
        pass

    @abstractmethod
    def feed_bytes(self, raw_bytes: bytes) -> list[NormalizedTelemetryEvent]:
        """Ingests raw byte chunks, decodes protocol frames, and returns normalized events."""
        pass

    @abstractmethod
    def decode_message(self, message_type: str, payload_dict: dict[str, Any]) -> NormalizedTelemetryEvent | None:
        """Decodes a single high-level telemetry payload into canonical NormalizedTelemetryEvent."""
        pass

    def dispatch_event(self, event: NormalizedTelemetryEvent) -> None:
        """Dispatches generated canonical event to the registered listener / gateway buffer."""
        self.stats.events_generated += 1
        if self.on_event_callback:
            self.on_event_callback(event)

    def get_stats(self) -> ConnectorStats:
        """Returns real-time connector operational metrics."""
        return self.stats
