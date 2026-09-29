"""B2: MQTT Telemetry Connector — Normalized event producer for MQTT broker streams.

Architecture Invariants:
- Implements TelemetryConnector (protocol-agnostic base) for MQTT.
- Connection config: host, port, topic_filter, client_id, qos, keep_alive_sec.
- Credentials (username/password) are NEVER stored inline — resolved at runtime
  from the platform secrets layer via secret_reference on DataSource.
- All received messages are deserialized as JSON and mapped to NormalizedTelemetryEvent.
- Messages that fail schema validation are counted as parse errors but do not crash
  the connector — they are discarded with a structured error log.
- Topic hierarchy: {prefix}/{organization_id}/{asset_id}/{event_type}
  or arbitrary flattened JSON blobs with a `source_asset_id` key.

Supported MQTT payload formats:
1. KOTA canonical JSON: already a NormalizedTelemetryEvent dict.
2. Simple sensor JSON: {"asset_id": ..., "sensor_code": ..., "value": ..., "unit": ...}
3. Flat OEM telemetry: {"device_sn": ..., "temperature": ..., "voltage": ...}
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

import structlog

from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryReadingItem,
)
from app.services.edge.connector_base import ConnectorState, TelemetryConnector

log = structlog.get_logger(__name__)

# Default MQTT QoS level for subscriptions (0 = at-most-once, 1 = at-least-once)
DEFAULT_QOS = 1
DEFAULT_PORT = 1883
DEFAULT_KEEPALIVE = 60


_TS_KEYS = ("event_timestamp", "timestamp", "time", "ts", "recorded_at")


def _payload_timestamp(payload: dict[str, Any]) -> datetime | None:
    """The device's own timestamp (epoch s/ms or ISO-8601) or None. Using arrival time for
    a buffered/late message would file it at the wrong moment and break ordering."""
    for key in _TS_KEYS:
        raw = payload.get(key)
        if raw is None or isinstance(raw, bool):
            continue
        try:
            if isinstance(raw, (int, float)):
                seconds = float(raw) / 1000.0 if float(raw) > 1e10 else float(raw)
                return datetime.fromtimestamp(seconds, tz=UTC)
            parsed = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except (ValueError, OverflowError, OSError):
            raise ValueError(f"Unparseable timestamp in field {key!r}: {raw!r}")
    return None


def _mqtt_event_id(prefix: str, connector_id: str, topic: str, payload: dict[str, Any], has_ts: bool) -> str:
    """Deterministic id so an at-least-once redelivery of the SAME message is a duplicate.
    Without a device timestamp the arrival SECOND is included, so identical readings sent
    later are still distinct events."""
    import hashlib
    import json as _json

    body = _json.dumps(payload, sort_keys=True, default=str)
    bucket = "" if has_ts else str(int(datetime.now(UTC).timestamp()))
    digest = hashlib.sha256(f"{connector_id}|{topic}|{bucket}|{body}".encode()).hexdigest()[:32]
    return f"{prefix}-{digest}"


class MQTTConnector(TelemetryConnector):
    """MQTT-protocol telemetry connector that produces NormalizedTelemetryEvent objects.

    This connector is intentionally agnostic about the MQTT client library —
    it delegates actual broker I/O to the caller (gateway_service or a
    Celery worker). The connector handles only:
    - Topic subscription configuration
    - Raw JSON payload parsing
    - Normalization to NormalizedTelemetryEvent
    - Stats / error tracking

    Integration pattern:
        connector = MQTTConnector(...)
        connector.connect("mqtt://broker:1883")
        # In MQTT message callback:
        events = connector.feed_bytes(raw_payload_bytes, topic="kota/telemetry/org-id/drone-1")
        for event in events:
            gateway.on_event(event)
    """

    def __init__(
        self,
        connector_id: str,
        source_system: str = "MQTT",
        topic_filter: str = "kota/telemetry/#",
        client_id: str | None = None,
        qos: int = DEFAULT_QOS,
        on_event_callback: Callable[[NormalizedTelemetryEvent], Any] | None = None,
    ) -> None:
        super().__init__(
            connector_id=connector_id,
            protocol="MQTT",
            on_event_callback=on_event_callback,
        )
        self.source_system = source_system
        self.topic_filter = topic_filter
        self.client_id = client_id or f"kota-mqtt-{connector_id[:8]}"
        self.qos = qos
        self._endpoint_uri: str = ""

    # ------------------------------------------------------------------
    # TelemetryConnector interface
    # ------------------------------------------------------------------

    def connect(self, endpoint_uri: str = "mqtt://localhost:1883", **kwargs: Any) -> bool:
        """Validates and stores connection endpoint; actual MQTT connect is delegated to caller."""
        self._endpoint_uri = endpoint_uri
        self.state = ConnectorState.CONNECTED
        self.stats.state = ConnectorState.CONNECTED
        self.stats.connected_at = datetime.now(UTC)
        log.info(
            "mqtt_connector.connected",
            connector_id=self.connector_id,
            endpoint=endpoint_uri,
            topic_filter=self.topic_filter,
        )
        return True

    def disconnect(self) -> None:
        self.state = ConnectorState.DISCONNECTED
        self.stats.state = ConnectorState.DISCONNECTED
        log.info("mqtt_connector.disconnected", connector_id=self.connector_id)

    def feed_bytes(self, raw_bytes: bytes, topic: str = "", **kwargs: Any) -> list[NormalizedTelemetryEvent]:
        """Deserializes a raw MQTT message payload and normalizes it to telemetry events.

        Args:
            raw_bytes: The MQTT message payload bytes.
            topic: The MQTT topic the message arrived on (used for asset_id extraction).

        Returns:
            List of zero or more NormalizedTelemetryEvent objects.
        """
        self.stats.messages_received += 1
        self.stats.bytes_received += len(raw_bytes)
        self.stats.last_message_at = datetime.now(UTC)

        if self.state != ConnectorState.CONNECTED:
            self.state = ConnectorState.STREAMING
            self.stats.state = ConnectorState.STREAMING

        try:
            payload_dict = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.stats.parse_errors += 1
            log.warning(
                "mqtt_connector.parse_error",
                connector_id=self.connector_id,
                error=str(exc),
                topic=topic,
            )
            return []

        event = self.decode_message(topic, payload_dict)
        if event:
            self.dispatch_event(event)
            return [event]
        return []

    def decode_message(
        self, message_type: str, payload_dict: dict[str, Any]
    ) -> NormalizedTelemetryEvent | None:
        """Decodes a deserialized MQTT JSON payload into a NormalizedTelemetryEvent.

        Supports three payload formats:
        1. Canonical KOTA format (has 'source_system', 'source_event_id', 'source_asset_id').
        2. Compact sensor format (has 'sensor_code', 'value', 'unit').
        3. Flat OEM format (arbitrary key-value pairs with at least 'device_sn' or 'asset_id').
        """
        topic = message_type  # topic string passed as message_type per base interface

        try:
            # --- Format 1: Already canonical KOTA NormalizedTelemetryEvent ---
            if "source_system" in payload_dict and "source_event_id" in payload_dict:
                return self._decode_canonical(payload_dict, topic)

            # --- Format 2: Compact sensor reading ---
            if "sensor_code" in payload_dict and "value" in payload_dict:
                return self._decode_sensor_reading(payload_dict, topic)

            # --- Format 3: Flat OEM blob ---
            return self._decode_flat_oem(payload_dict, topic)

        except Exception as exc:
            self.stats.parse_errors += 1
            log.warning(
                "mqtt_connector.decode_error",
                connector_id=self.connector_id,
                error=str(exc),
                topic=topic,
            )
            return None

    # ------------------------------------------------------------------
    # Format-specific decoders
    # ------------------------------------------------------------------

    def _decode_canonical(
        self, payload: dict[str, Any], topic: str
    ) -> NormalizedTelemetryEvent | None:
        """Validates and re-constructs a canonical NormalizedTelemetryEvent from dict."""
        try:
            # Ensure event_timestamp is a datetime
            if isinstance(payload.get("event_timestamp"), str):
                payload["event_timestamp"] = datetime.fromisoformat(
                    payload["event_timestamp"].replace("Z", "+00:00")
                )
            return NormalizedTelemetryEvent(**payload)
        except Exception as exc:
            log.warning("mqtt_connector.canonical_decode_error", error=str(exc), topic=topic)
            return None

    def _decode_sensor_reading(
        self, payload: dict[str, Any], topic: str
    ) -> NormalizedTelemetryEvent:
        """Decodes a compact single-sensor reading payload."""
        # Extract asset ID from topic segments or payload
        asset_id, asset_conflict = self._resolve_asset_identifier(topic, payload)
        sensor_code = str(payload.get("sensor_code", "UNKNOWN"))
        value = float(payload["value"])
        unit = str(payload.get("unit", ""))
        measurement_type = str(payload.get("measurement_type", sensor_code.upper()))
        data_quality = str(payload.get("data_quality", "VALID"))

        reading = TelemetryReadingItem(
            sensor_code=sensor_code,
            sensor_type=str(payload.get("sensor_type", "TELEMETRY")),
            measurement_type=measurement_type,
            value=value,
            unit=unit,
            data_quality=data_quality,
        )

        device_ts = _payload_timestamp(payload)
        return NormalizedTelemetryEvent(
            source_system=self.source_system,
            source_event_id=_mqtt_event_id("MQTT", self.connector_id, topic, payload, device_ts is not None),
            source_asset_id=asset_id,
            event_type="TELEMETRY_PING",
            event_timestamp=device_ts or datetime.now(UTC),
            readings=[reading],
            raw_metadata={
                "topic": topic,
                "format": "compact_sensor",
                "timestamp_source": "SOURCE" if device_ts else "RECEIVED",
                **({"asset_identifier_conflict": asset_conflict} if asset_conflict else {}),
            },
        )

    def _decode_flat_oem(
        self, payload: dict[str, Any], topic: str
    ) -> NormalizedTelemetryEvent:
        """Decodes a flat OEM blob into sensor readings by scanning numeric fields."""
        asset_id, asset_conflict = self._resolve_asset_identifier(topic, payload)

        readings: list[TelemetryReadingItem] = []
        skip_keys = {
            "device_sn", "asset_id", "serial_number", "timestamp", "time", "ts",
            "event_timestamp", "recorded_at", "event_type", "source_system",
        }
        for key, val in payload.items():
            if key in skip_keys or isinstance(val, bool):  # a flag is not a measurement
                continue
            try:
                fval = float(val)
                if not (-1e12 < fval < 1e12):
                    continue  # sanity guard for poison values
                readings.append(
                    TelemetryReadingItem(
                        sensor_code=key.upper()[:64],
                        sensor_type="OEM_TELEMETRY",
                        measurement_type=key.upper()[:64],
                        value=fval,
                        unit="",
                        data_quality="VALID",
                    )
                )
            except (TypeError, ValueError):
                continue  # non-numeric field, skip

        device_ts = _payload_timestamp(payload)
        return NormalizedTelemetryEvent(
            source_system=self.source_system,
            source_event_id=_mqtt_event_id("MQTT-OEM", self.connector_id, topic, payload, device_ts is not None),
            source_asset_id=asset_id,
            event_type="TELEMETRY_PING",
            event_timestamp=device_ts or datetime.now(UTC),
            readings=readings,
            raw_metadata={
                "topic": topic,
                "format": "flat_oem",
                "original_keys": list(payload.keys()),
                "timestamp_source": "SOURCE" if device_ts else "RECEIVED",
                **({"asset_identifier_conflict": asset_conflict} if asset_conflict else {}),
            },
        )

    def _resolve_asset_identifier(
        self, topic: str, payload: dict[str, Any]
    ) -> tuple[str, dict[str, str] | None]:
        """Asset identity: an explicit identifier IN the payload outranks anything inferred from
        the topic (a topic's last segment is often an event type such as 'PING', not an asset).
        If both are present and differ, the payload wins and the conflict is recorded in the
        event metadata so it is visible downstream instead of silently choosing."""
        explicit = next(
            (str(payload[k]).strip() for k in ("asset_id", "serial_number", "device_sn")
             if payload.get(k) not in (None, "")),
            None,
        )
        from_topic = self._extract_asset_from_topic(topic)
        if explicit:
            conflict = (
                {"topic": from_topic, "payload": explicit}
                if from_topic and from_topic != explicit else None
            )
            return explicit, conflict
        return (from_topic or "UNKNOWN"), None

    def _extract_asset_from_topic(self, topic: str) -> str | None:
        """Extracts an asset ID from a structured MQTT topic.

        Expected topic format: {prefix}/{org_id}/{asset_id}/{event_type}
        Returns the third segment if it looks like a valid UUID or asset reference.
        """
        if not topic:
            return None
        parts = topic.split("/")
        # Look for a segment that resembles a UUID
        for part in parts:
            try:
                uuid.UUID(part)
                return part
            except ValueError:
                continue
        # Fall back to last meaningful segment
        return parts[-1] if len(parts) > 1 else None

    def get_connection_config(self) -> dict[str, Any]:
        """Returns the active connection configuration (no secrets)."""
        return {
            "endpoint_uri": self._endpoint_uri,
            "topic_filter": self.topic_filter,
            "client_id": self.client_id,
            "qos": self.qos,
            "source_system": self.source_system,
        }
