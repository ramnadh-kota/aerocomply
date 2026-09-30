"""TCP MAVLink listener (server mode): vehicles / ground stations / gateways connect IN to one port -> one data source.

Same fail-closed rules as UDP (see udp_mavlink.py): the peer address must be in `allowed_cidrs` (checked when the
connection is accepted) and/or frames must be MAVLink-2 signed. Additional TCP bounds:
  * at most MAX_CONNECTIONS concurrent peers per listener; further connects are closed immediately
  * a peer that sends nothing for IDLE_TIMEOUT seconds is disconnected
  * received bytes are only buffered through the bounded JobSink (drop + count when full), never unboundedly
Framing is handled downstream by the MAVLink connector (it buffers partial frames per data source), so this layer just
forwards the byte stream."""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.listeners.common import RECEIVED, UP, JobSink, ip_allowed
from app.listeners.udp_mavlink import UdpSettings

log = structlog.get_logger("listener.tcp")
MAX_CONNECTIONS = 64
IDLE_TIMEOUT = 60.0
READ_CHUNK = 4096


async def run_tcp(
    sink: JobSink, settings: UdpSettings, stop: asyncio.Event, *, flush_interval: float = 1.0, on_ready: Any = None,
    idle_timeout: float = IDLE_TIMEOUT, max_connections: int = MAX_CONNECTIONS,
) -> None:
    active = 0
    writers: set[asyncio.StreamWriter] = set()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal active
        peer = writer.get_extra_info("peername") or ("unknown", 0)
        writers.add(writer)
        try:
            if settings.nets and not ip_allowed(str(peer[0]), settings.nets):
                RECEIVED.inc(protocol="tcp", outcome="source_not_allowed")
                return
            if active >= max_connections:
                RECEIVED.inc(protocol="tcp", outcome="too_many_connections")
                return
            active += 1
            try:
                while not stop.is_set():
                    try:
                        data = await asyncio.wait_for(reader.read(READ_CHUNK), timeout=idle_timeout)
                    except TimeoutError:
                        RECEIVED.inc(protocol="tcp", outcome="idle_timeout")
                        return
                    if not data:
                        return
                    RECEIVED.inc(protocol="tcp", outcome="accepted" if sink.add(data) else "buffer_full")
            finally:
                active -= 1
        except (ConnectionError, OSError):
            pass                                   # a peer resetting the connection is routine, never fatal
        finally:
            writers.discard(writer)
            writer.close()

    server = await asyncio.start_server(handle, host=settings.bind, port=settings.port)
    UP.set(1, protocol="tcp")
    if on_ready:
        on_ready(server.sockets[0].getsockname())
    log.info("tcp.listening", bind=settings.bind, port=settings.port, signed=settings.signed,
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
        server.close()
        for w in list(writers):                  # do not wait up to idle_timeout for quiet peers: drop them now
            w.close()
        try:
            await asyncio.wait_for(server.wait_closed(), timeout=5.0)
        except TimeoutError:
            log.warning("tcp.shutdown_timeout", data_source_id=str(sink.data_source_id))
        await asyncio.to_thread(sink.flush)
        UP.set(0, protocol="tcp")
