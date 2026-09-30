"""In-process MQTT broker TEST DOUBLE. Not production infrastructure: it proves the listener's subscribe / reconnect /
filtering logic, nothing about a real broker's TLS, auth, persistence or QoS semantics."""
from __future__ import annotations

from collections.abc import Callable

from app.listeners.mqtt import topic_matches


class InMemoryBroker:
    def __init__(self) -> None:
        self.clients: list[InMemoryClient] = []
        self.fail_connects = 0            # next N connect() calls raise (broker down)
        self.connect_log: list[dict] = []

    def client(self) -> InMemoryClient:
        c = InMemoryClient(self)
        self.clients.append(c)
        return c

    def publish(self, topic: str, payload: bytes) -> int:
        n = 0
        for c in list(self.clients):
            if c.connected and any(topic_matches(f, topic) for f in c.subscriptions):
                c._on_message(topic, payload)
                n += 1
        return n

    def drop_all_connections(self) -> None:
        for c in list(self.clients):
            if c.connected:
                c.connected = False
                c._on_disconnect()


class InMemoryClient:
    def __init__(self, broker: InMemoryBroker) -> None:
        self.broker, self.connected = broker, False
        self.subscriptions: list[str] = []
        self._on_message: Callable[[str, bytes], None] = lambda t, p: None
        self._on_disconnect: Callable[[], None] = lambda: None

    def set_message_handler(self, handler) -> None:
        self._on_message = handler

    def set_disconnect_handler(self, handler) -> None:
        self._on_disconnect = handler

    def connect(self, host, port, *, username, password, tls, keepalive, client_id) -> None:
        self.broker.connect_log.append({"host": host, "port": port, "username": username, "tls": tls,
                                        "has_password": password is not None, "client_id": client_id})
        if self.broker.fail_connects > 0:
            self.broker.fail_connects -= 1
            raise ConnectionRefusedError("broker down")
        self.connected = True

    def subscribe(self, topic: str, qos: int) -> None:
        self.subscriptions.append(topic)

    def disconnect(self) -> None:
        self.connected = False
