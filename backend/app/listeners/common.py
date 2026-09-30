"""Shared listener plumbing: metrics, CIDR allow-list, and the buffered, back-pressured job sink."""
from __future__ import annotations

import ipaddress
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.metrics import REGISTRY, Counter, Gauge
from app.models.background_job import BackgroundJob, JobStatus
from app.services import job_handlers, job_service

log = structlog.get_logger("listener")

RECEIVED = REGISTRY.register(Counter("kota_listener_messages_total", "Messages received by protocol and outcome"))
DROPPED = REGISTRY.register(Counter("kota_listener_dropped_total", "Messages dropped before queueing, by protocol and reason"))
FLUSHES = REGISTRY.register(Counter("kota_listener_flushes_total", "Buffers handed to the job queue, by protocol"))
RECONNECTS = REGISTRY.register(Counter("kota_listener_reconnects_total", "Broker reconnect attempts, by protocol"))
UP = REGISTRY.register(Gauge("kota_listener_up", "1 while a listener is running, by protocol"))

MAX_BUFFER_BYTES = 256 * 1024          # in-memory ceiling per source; beyond it new data is dropped, never buffered
FLUSH_BYTES = 32 * 1024
DEFAULT_MAX_QUEUE_DEPTH = 5_000        # QUEUED jobs per organization before the listener sheds load

SessionFactory = Callable[[], AbstractContextManager[Session]]


def parse_cidrs(values: list[str] | None) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for v in values or []:
        nets.append(ipaddress.ip_network(str(v).strip(), strict=False))   # ValueError on garbage -> caller refuses to start
    return nets


def ip_allowed(ip: str, nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in n for n in nets)


class JobSink:
    """Collects raw bytes for one data source and enqueues them as ingest jobs.

    * bounded memory: over MAX_BUFFER_BYTES new data is dropped and counted (a listener must never OOM)
    * back-pressure: if the organization already has max_queue_depth QUEUED jobs, the flush is dropped and counted
      instead of growing the queue without limit (the sender / link recovers; ingestion stays healthy)
    * thread-safe: datagram callbacks and the flush timer may run on different threads"""

    def __init__(
        self, *, organization_id: uuid.UUID, data_source_id: uuid.UUID, session_factory: SessionFactory,
        protocol: str, max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH, topic: str | None = None,
    ) -> None:
        self.organization_id, self.data_source_id, self.protocol = organization_id, data_source_id, protocol
        self.topic, self.max_queue_depth = topic, max_queue_depth
        self._session_factory = session_factory
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._last_flush = time.monotonic()

    def add(self, data: bytes) -> bool:
        """Buffer `data`; returns False if it was dropped for lack of buffer space."""
        with self._lock:
            if len(self._buf) + len(data) > MAX_BUFFER_BYTES:
                DROPPED.inc(protocol=self.protocol, reason="buffer_full")
                return False
            self._buf.extend(data)
            return True

    def should_flush(self, interval: float) -> bool:
        with self._lock:
            return bool(self._buf) and (len(self._buf) >= FLUSH_BYTES or time.monotonic() - self._last_flush >= interval)

    def flush(self) -> bool:
        """Enqueue everything buffered. Returns True if a job was created."""
        with self._lock:
            data, self._buf = bytes(self._buf), bytearray()
            self._last_flush = time.monotonic()
        if not data:
            return False
        return self._enqueue(data, self.topic)

    def submit(self, data: bytes, topic: str | None = None) -> bool:
        """Enqueue one message right away (MQTT: one job per message, topic preserved)."""
        return self._enqueue(data, topic)

    def _enqueue(self, data: bytes, topic: str | None) -> bool:
        try:
            with self._session_factory() as db:
                depth = db.scalar(
                    select(func.count(BackgroundJob.id)).where(
                        BackgroundJob.organization_id == self.organization_id, BackgroundJob.status == JobStatus.QUEUED
                    )
                ) or 0
                if depth >= self.max_queue_depth:
                    DROPPED.inc(protocol=self.protocol, reason="backpressure")
                    log.warning("listener.backpressure_drop", organization_id=str(self.organization_id),
                                data_source_id=str(self.data_source_id), queue_depth=depth)
                    return False
                job_service.enqueue(
                    db, job_type=job_handlers.INGEST, organization_id=self.organization_id,
                    data_source_id=self.data_source_id, payload={"topic": topic}, payload_blob=data,
                    correlation_id=f"listener-{self.protocol.lower()}",
                )
                db.commit()
        except Exception:  # noqa: BLE001 - a DB outage must not crash the listener; the data is counted as dropped
            DROPPED.inc(protocol=self.protocol, reason="enqueue_error")
            log.exception("listener.enqueue_failed", data_source_id=str(self.data_source_id))
            return False
        FLUSHES.inc(protocol=self.protocol)
        return True


def listener_config(connection_config: dict[str, Any] | None) -> dict[str, Any]:
    return dict((connection_config or {}).get("listen") or {})
