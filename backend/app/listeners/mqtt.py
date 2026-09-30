"""MQTT subscriber listener: one data source -> one broker subscription -> one tenant.

data source connection_config:
  {"listen": {"host": "broker.example.com", "port": 8883, "tls": true, "username": "kota", "topics": ["fleet/+/telemetry"],
              "qos": 1, "keepalive": 60, "client_id": "kota-org1"}}      + secret_reference -> broker password

The broker client is abstracted (`MQTTClientLike`): production uses paho-mqtt (`pip install paho-mqtt`), tests use the
in-memory broker in app/listeners/testing.py. The in-memory broker is a TEST DOUBLE, not production infrastructure;
behaviour against a real broker (TLS, auth, QoS 1 redelivery, retained messages) is EXTERNAL VALIDATION REQUIRED.

Safety: plaintext MQTT to a non-loopback broker is refused unless listen.allow_insecure is true; the password is
resolved at runtime from the secrets layer and is never logged; messages are only accepted on subscribed topics;
oversized payloads are dropped. At-least-once redelivery is harmless: the MQTT connector derives a deterministic event
id, so duplicates are counted as duplicates.
"""
from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from app.core import secrets as secrets_layer
from app.listeners.common import RECEIVED, RECONNECTS, UP, JobSink, listener_config
from app.listeners.udp_mavlink import ListenerRefused

log = structlog.get_logger("listener.mqtt")
MAX_PAYLOAD = 256 * 1024
BACKOFF_MIN, BACKOFF_MAX = 1.0, 60.0


class MQTTClientLike(Protocol):
    def connect(self, host: str, port: int, *, username: str | None, password: str | None, tls: bool,
                keepalive: int, client_id: str) -> None: ...
    def subscribe(self, topic: str, qos: int) -> None: ...
    def set_message_handler(self, handler: Callable[[str, bytes], None]) -> None: ...
    def set_disconnect_handler(self, handler: Callable[[], None]) -> None: ...
    def disconnect(self) -> None: ...


def topic_matches(topic_filter: str, topic: str) -> bool:
    """MQTT topic filter match: '+' one level, '#' the rest (must be last)."""
    f, t = topic_filter.split("/"), topic.split("/")
    for i, part in enumerate(f):
        if part == "#":
            return i == len(f) - 1
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(f) == len(t)


@dataclass
class MqttSettings:
    host: str
    port: int
    tls: bool
    username: str | None
    topics: list[str]
    qos: int = 1
    keepalive: int = 60
    client_id: str = "kota-listener"
    password: str | None = field(default=None, repr=False)   # never in logs / repr


def validate_mqtt_config(connection_config: dict[str, Any] | None, secret_reference: str | None) -> MqttSettings:
    cfg = listener_config(connection_config)
    if not cfg:
        raise ListenerRefused("no 'listen' configuration")
    host = str(cfg.get("host") or "").strip()
    if not host:
        raise ListenerRefused("listen.host is required")
    tls = bool(cfg.get("tls", False))
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if not tls and not loopback and not cfg.get("allow_insecure"):
        raise ListenerRefused("refusing plaintext MQTT to a non-loopback broker (set listen.tls, or allow_insecure)")
    topics = [str(t) for t in (cfg.get("topics") or []) if str(t).strip()]
    if not topics:
        raise ListenerRefused("listen.topics must list at least one topic filter")
    if any("#" in t and not t.endswith("#") for t in topics):
        raise ListenerRefused("'#' is only valid as the last level of a topic filter")
    qos = int(cfg.get("qos", 1))
    if qos not in (0, 1, 2):
        raise ListenerRefused("listen.qos must be 0, 1 or 2")
    return MqttSettings(
        host=host, port=int(cfg.get("port") or (8883 if tls else 1883)), tls=tls,
        username=cfg.get("username"), topics=topics, qos=qos, keepalive=int(cfg.get("keepalive", 60)),
        client_id=str(cfg.get("client_id") or "kota-listener")[:64], password=secrets_layer.resolve(secret_reference),
    )


class MqttListener:
    def __init__(self, sink: JobSink, settings: MqttSettings, client_factory: Callable[[], MQTTClientLike]) -> None:
        self.sink, self.settings, self._client_factory = sink, settings, client_factory
        self.connected = asyncio.Event()
        self._lost = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    def on_message(self, topic: str, payload: bytes) -> None:
        if not any(topic_matches(f, topic) for f in self.settings.topics):
            RECEIVED.inc(protocol="mqtt", outcome="unsubscribed_topic")
            return
        if not payload or len(payload) > MAX_PAYLOAD:
            RECEIVED.inc(protocol="mqtt", outcome="bad_size")
            return
        RECEIVED.inc(protocol="mqtt", outcome="accepted" if self.sink.submit(payload, topic) else "not_queued")

    def _on_disconnect(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._lost.set)

    async def run(self, stop: asyncio.Event) -> None:
        """Connect, subscribe, and stay connected; reconnect with exponential backoff until `stop` is set."""
        self._loop = asyncio.get_running_loop()
        delay = BACKOFF_MIN
        while not stop.is_set():
            client = self._client_factory()
            client.set_message_handler(self.on_message)
            client.set_disconnect_handler(self._on_disconnect)
            self._lost.clear()
            try:
                s = self.settings
                client.connect(s.host, s.port, username=s.username, password=s.password, tls=s.tls,
                               keepalive=s.keepalive, client_id=s.client_id)
                for t in s.topics:
                    client.subscribe(t, s.qos)
                self.connected.set()
                UP.set(1, protocol="mqtt")
                delay = BACKOFF_MIN
                log.info("mqtt.connected", host=s.host, port=s.port, tls=s.tls, topics=s.topics,
                         data_source_id=str(self.sink.data_source_id))
                await asyncio.wait({asyncio.ensure_future(stop.wait()), asyncio.ensure_future(self._lost.wait())},
                                   return_when=asyncio.FIRST_COMPLETED)
            except Exception as exc:  # noqa: BLE001 - any connect/subscribe failure => backoff and retry
                log.warning("mqtt.connect_failed", error=type(exc).__name__, retry_in=delay)
            finally:
                self.connected.clear()
                UP.set(0, protocol="mqtt")
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
            if stop.is_set():
                break
            RECONNECTS.inc(protocol="mqtt")
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except TimeoutError:
                pass
            delay = min(BACKOFF_MAX, delay * 2)


class PahoClient:  # pragma: no cover - needs paho-mqtt and a real broker (external validation)
    """paho-mqtt 2.x adapter. paho runs its own network thread and re-subscribes are done by MqttListener."""

    def __init__(self) -> None:
        try:
            import paho.mqtt.client as paho
        except ImportError as exc:
            raise ListenerRefused("paho-mqtt is not installed (pip install paho-mqtt)") from exc
        self._paho = paho
        self._c: Any = None
        self._on_message: Callable[[str, bytes], None] = lambda t, p: None
        self._on_disconnect: Callable[[], None] = lambda: None

    def set_message_handler(self, handler: Callable[[str, bytes], None]) -> None:
        self._on_message = handler

    def set_disconnect_handler(self, handler: Callable[[], None]) -> None:
        self._on_disconnect = handler

    def connect(self, host: str, port: int, *, username: str | None, password: str | None, tls: bool,
                keepalive: int, client_id: str) -> None:
        c = self._paho.Client(self._paho.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            c.username_pw_set(username, password)
        if tls:
            c.tls_set()                      # system CA bundle, certificate + hostname verification ON
        c.on_message = lambda _c, _u, m: self._on_message(m.topic, bytes(m.payload))
        c.on_disconnect = lambda *_a, **_k: self._on_disconnect()
        c.connect(host, port, keepalive)
        c.loop_start()
        self._c = c

    def subscribe(self, topic: str, qos: int) -> None:
        self._c.subscribe(topic, qos)

    def disconnect(self) -> None:
        if self._c is not None:
            self._c.loop_stop()
            self._c.disconnect()
