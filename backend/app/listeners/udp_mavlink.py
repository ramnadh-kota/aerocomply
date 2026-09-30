"""UDP MAVLink listener: one UDP port -> one data source -> one tenant.

data source connection_config:
  {"listen": {"bind": "0.0.0.0", "udp_port": 14550, "allowed_cidrs": ["203.0.113.0/24"]}, "system_id_map": {...},
   "require_signing": true}   # + secret_reference -> MAVLink 2 signing key

FAIL-CLOSED: UDP has no sender authentication, so anyone who can reach the port could inject telemetry into the
tenant. The listener therefore REFUSES to start unless at least one protection is configured:
  * allowed_cidrs (datagrams from other addresses are dropped), and/or
  * message signing (secret_reference resolves to a key and require_signing is not false): unsigned/forged frames
    are rejected by the connector at ingest time.
(Source addresses can be spoofed on UDP; signing is the real authentication, the CIDR list is defence in depth.)
"""
from __future__ import annotations

import asyncio
import ipaddress
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core import secrets as secrets_layer
from app.listeners.common import RECEIVED, UP, JobSink, ip_allowed, listener_config, parse_cidrs

log = structlog.get_logger("listener.udp")
MAX_DATAGRAM = 2048  # MAVLink frames are <= 280 bytes; larger datagrams are not MAVLink


class ListenerRefused(Exception):
    """The configuration is unsafe or invalid; the listener must not start (reason is operator-visible)."""


@dataclass
class UdpSettings:
    bind: str
    port: int
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = field(default_factory=list)
    signed: bool = False
    transport: str = "udp"


def validate_udp_config(connection_config: dict[str, Any] | None, secret_reference: str | None) -> UdpSettings:
    cfg = listener_config(connection_config)
    if not cfg:
        raise ListenerRefused("no 'listen' configuration")
    if bool(cfg.get("udp_port")) == bool(cfg.get("tcp_port")):
        raise ListenerRefused("set exactly one of listen.udp_port / listen.tcp_port")
    transport = "tcp" if cfg.get("tcp_port") else "udp"
    try:
        port = int(cfg.get("tcp_port") or cfg.get("udp_port") or 0)
    except (TypeError, ValueError) as exc:
        raise ListenerRefused(f"listen.{transport}_port must be a number") from exc
    if not 1 <= port <= 65535:
        raise ListenerRefused(f"listen.{transport}_port out of range")
    bind = str(cfg.get("bind") or "127.0.0.1")
    try:
        ipaddress.ip_address(bind)
        nets = parse_cidrs(cfg.get("allowed_cidrs"))
    except ValueError as exc:
        raise ListenerRefused(f"invalid bind address or CIDR: {exc}") from exc
    signed = bool(secrets_layer.resolve(secret_reference)) and (connection_config or {}).get("require_signing") is not False
    if not nets and not signed:
        raise ListenerRefused(
            "refusing to listen: configure listen.allowed_cidrs and/or MAVLink signing (secret_reference)"
        )
    return UdpSettings(bind=bind, port=port, nets=nets, signed=signed, transport=transport)


class MavlinkUdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, sink: JobSink, settings: UdpSettings) -> None:
        self.sink, self.settings = sink, settings

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        if len(data) > MAX_DATAGRAM:
            RECEIVED.inc(protocol="udp", outcome="oversize")
            return
        if self.settings.nets and not ip_allowed(addr[0], self.settings.nets):
            RECEIVED.inc(protocol="udp", outcome="source_not_allowed")
            return
        RECEIVED.inc(protocol="udp", outcome="accepted" if self.sink.add(data) else "buffer_full")

    def error_received(self, exc: Exception) -> None:  # ICMP errors etc.: never fatal
        log.warning("udp.error_received", error=type(exc).__name__)


async def run_udp(
    sink: JobSink, settings: UdpSettings, stop: asyncio.Event, *, flush_interval: float = 1.0,
    on_ready: Any = None,
) -> None:
    """Serve until `stop` is set, then flush what is buffered (no accepted datagram is lost on shutdown)."""
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: MavlinkUdpProtocol(sink, settings), local_addr=(settings.bind, settings.port)
    )
    UP.set(1, protocol="udp")
    if on_ready:
        on_ready(transport.get_extra_info("sockname"))
    log.info("udp.listening", bind=settings.bind, port=settings.port, signed=settings.signed,
             data_source_id=str(sink.data_source_id))
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=flush_interval)
            except TimeoutError:
                pass
            if sink.should_flush(flush_interval):
                await asyncio.to_thread(sink.flush)
    finally:
        transport.close()
        await asyncio.to_thread(sink.flush)
        UP.set(0, protocol="udp")
