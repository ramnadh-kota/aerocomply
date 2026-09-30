"""Listener supervisor:  python -m app.listeners

Starts one listener per ACTIVE data source whose connection_config has a "listen" section, and reconciles every
`reconcile_seconds` (a source paused, edited, decommissioned or newly activated is picked up without a restart).
SIGINT/SIGTERM stop every listener and flush buffered data before exit. A misconfigured or unsafe source is refused
(recorded in the source's last_error, visible in the Data Sources UI) and never blocks the others.

Deployment: run ONE supervisor per UDP bind address/port set (a port can only be bound once) and one or more
`python -m app.worker` processes to execute the queued jobs."""
from __future__ import annotations

import asyncio
import hashlib
import json
import signal
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.listeners.common import DEFAULT_MAX_QUEUE_DEPTH, JobSink, SessionFactory
from app.listeners.mqtt import MqttListener, PahoClient, validate_mqtt_config
from app.listeners.udp_mavlink import ListenerRefused, run_udp, validate_udp_config
from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus

log = structlog.get_logger("listener.supervisor")


@contextmanager
def default_session():
    with SessionLocal() as db:
        yield db


@dataclass
class _Running:
    fingerprint: str
    stop: asyncio.Event
    task: asyncio.Task


def _fingerprint(s: DataSource) -> str:
    blob = json.dumps([s.status, s.connector_type, s.connection_config, s.secret_reference], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _record_refusal(session_factory: SessionFactory, source_id: Any, reason: str) -> None:
    try:
        with session_factory() as db:
            src = db.get(DataSource, source_id)
            if src is not None:
                src.last_error = f"listener refused: {reason}"[:512]
                db.commit()
    except Exception:  # noqa: BLE001 - best effort; the refusal is also logged
        log.exception("listener.record_refusal_failed")


class Supervisor:
    def __init__(
        self, *, session_factory: SessionFactory = default_session, reconcile_seconds: float = 30.0,
        mqtt_client_factory: Callable[[], Any] = PahoClient, max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH,
        flush_interval: float = 1.0,
    ) -> None:
        self.session_factory, self.reconcile_seconds = session_factory, reconcile_seconds
        self.mqtt_client_factory, self.max_queue_depth, self.flush_interval = mqtt_client_factory, max_queue_depth, flush_interval
        self.running: dict[Any, _Running] = {}
        self.refused: dict[Any, str] = {}

    def _wanted(self) -> dict[Any, DataSource]:
        with self.session_factory() as db:
            rows = db.execute(
                select(DataSource).where(
                    DataSource.status == DataSourceStatus.ACTIVE,
                    DataSource.connector_type.in_([DataSourceConnectorType.MAVLINK, DataSourceConnectorType.MQTT]),
                )
            ).scalars().all()
            wanted = {}
            for r in rows:
                if (r.connection_config or {}).get("listen"):
                    db.expunge(r)
                    wanted[r.id] = r
            return wanted

    async def reconcile(self) -> None:
        wanted = await asyncio.to_thread(self._wanted)
        for sid in list(self.running):
            r = self.running[sid]
            if sid not in wanted or r.fingerprint != _fingerprint(wanted[sid]) or r.task.done():
                r.stop.set()
                await asyncio.gather(r.task, return_exceptions=True)
                del self.running[sid]
        for sid, src in wanted.items():
            if sid in self.running:
                continue
            fp = _fingerprint(src)
            if self.refused.get(sid) == fp:
                continue                      # unchanged and already refused: do not spam
            try:
                task, stop = self._start(src)
            except ListenerRefused as exc:
                self.refused[sid] = fp
                log.warning("listener.refused", data_source_id=str(sid), reason=str(exc))
                await asyncio.to_thread(_record_refusal, self.session_factory, sid, str(exc))
                continue
            self.refused.pop(sid, None)
            self.running[sid] = _Running(fp, stop, task)

    def _start(self, src: DataSource) -> tuple[asyncio.Task, asyncio.Event]:
        stop = asyncio.Event()
        if src.connector_type == DataSourceConnectorType.MAVLINK:
            cfg = validate_udp_config(src.connection_config, src.secret_reference)
            sink = JobSink(organization_id=src.organization_id, data_source_id=src.id,
                           session_factory=self.session_factory, protocol="udp", max_queue_depth=self.max_queue_depth)
            coro = run_udp(sink, cfg, stop, flush_interval=self.flush_interval)
        else:
            mcfg = validate_mqtt_config(src.connection_config, src.secret_reference)
            sink = JobSink(organization_id=src.organization_id, data_source_id=src.id,
                           session_factory=self.session_factory, protocol="mqtt", max_queue_depth=self.max_queue_depth)
            coro = MqttListener(sink, mcfg, self.mqtt_client_factory).run(stop)
        return asyncio.create_task(coro, name=f"listener-{src.id}"), stop

    async def run(self, stop: asyncio.Event) -> None:
        log.info("supervisor.started")
        while not stop.is_set():
            try:
                await self.reconcile()
            except Exception:  # noqa: BLE001 - a DB blip must not kill running listeners
                log.exception("supervisor.reconcile_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.reconcile_seconds)
            except TimeoutError:
                pass
        await self.shutdown()

    async def shutdown(self) -> None:
        for r in self.running.values():
            r.stop.set()
        await asyncio.gather(*(r.task for r in self.running.values()), return_exceptions=True)
        self.running.clear()
        log.info("supervisor.stopped")


def main() -> None:
    async def _amain() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows event loops
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop.set))
        await Supervisor().run(stop)

    asyncio.run(_amain())


if __name__ == "__main__":
    main()
