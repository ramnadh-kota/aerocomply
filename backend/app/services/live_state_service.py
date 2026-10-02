"""C4: latest drone live state, read APIs and the SSE broker.

Single writer: `apply_event`, called by acquisition_service after an event is PROCESSED (no second ingest path).
PostgreSQL (`drone_live_state`) is the authority; the broker is an in-process fan-out for connected browsers only.
Broker state (cursor, replay window) is process-local by design: after a restart or on a different worker the cursor
epoch differs, the server answers `resync_required`, and the client re-fetches the REST snapshot. Nothing is lost
because every update is already in the database.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import event as sa_event
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.asset import Asset, AssetType
from app.models.drone_live_state import DroneLiveState
from app.models.telemetry import EdgeDevice
from app.schemas.live_state import (
    SCHEMA_VERSION,
    LiveIdentityV1,
    LiveStateV1,
    compute_freshness,
)
from app.schemas.telemetry import NormalizedTelemetryEvent
from app.services import device_auth_service

log = structlog.get_logger(__name__)

_GROUPS = ("position", "motion", "attitude", "battery", "mode", "mission")
REPLAY_WINDOW = 500
SUBSCRIBER_QUEUE = 256


# --------------------------------------------------------------------------------------------------- broker
class Subscriber:
    def __init__(self, organization_id: uuid.UUID, loop: asyncio.AbstractEventLoop) -> None:
        self.organization_id = organization_id
        self.loop = loop
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE)
        self.overflowed = False

    def push(self, item: dict[str, Any]) -> None:
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            self.overflowed = True  # slow consumer: it is told to resync instead of silently missing events


class LiveBroker:
    """Per-tenant monotonic sequence. Event id = `<epoch>:<n>`; `epoch` changes on every process start."""

    def __init__(self, window: int = REPLAY_WINDOW) -> None:
        self.epoch = uuid.uuid4().hex[:8]
        self._lock = threading.Lock()
        self._n: dict[uuid.UUID, int] = defaultdict(int)
        self._window: dict[uuid.UUID, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=window))
        self._subs: list[Subscriber] = []

    def cursor(self, organization_id: uuid.UUID) -> str:
        return f"{self.epoch}:{self._n[organization_id]}"

    def publish(self, organization_id: uuid.UUID, type_: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._n[organization_id] += 1
            n = self._n[organization_id]
            item = {"id": f"{self.epoch}:{n}", "n": n, "type": type_, "data": data}
            self._window[organization_id].append(item)
            subs = [s for s in self._subs if s.organization_id == organization_id]
        for s in subs:
            try:
                s.loop.call_soon_threadsafe(s.push, item)
            except RuntimeError:  # loop closed
                self.unsubscribe(s)
        return item

    def subscribe(self, organization_id: uuid.UUID) -> Subscriber:
        sub = Subscriber(organization_id, asyncio.get_running_loop())
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    def replay_after(self, organization_id: uuid.UUID, last_event_id: str | None) -> list[dict[str, Any]] | None:
        """Events after `last_event_id`, or None when the cursor cannot be honoured (other epoch, malformed, ahead of
        the server, or older than the retained window): the caller must then send `resync_required`."""
        try:
            epoch, n_s = (last_event_id or "").split(":")
            n = int(n_s)
        except ValueError:
            return None
        with self._lock:
            current = self._n[organization_id]
            if epoch != self.epoch or n > current or n < 0:
                return None
            if n == current:
                return []
            win = list(self._window[organization_id])
            if not win or win[0]["n"] > n + 1:
                return None  # part of the gap was evicted
            return [e for e in win if e["n"] > n]


broker = LiveBroker()


# ------------------------------------------------------------------------------------------------ write path
def apply_event(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, event: NormalizedTelemetryEvent,
    data_source_id: uuid.UUID | None = None, received_at: datetime | None = None,
) -> DroneLiveState | None:
    """Upsert the latest state from a PROCESSED event. An event older than the stored state never overwrites it.
    Returns the row when applied, None when skipped (no live_state in the event, or out of order)."""
    live = (event.raw_metadata or {}).get("live_state")
    if not live:
        return None
    received_at = received_at or datetime.now(UTC)
    row = db.execute(
        select(DroneLiveState).where(
            DroneLiveState.asset_id == asset_id, DroneLiveState.organization_id == organization_id
        ).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        row = DroneLiveState(
            organization_id=organization_id, asset_id=asset_id, state_version=1, event_count=1,
            last_event_at=event.event_timestamp, last_received_at=received_at, payload=live,
            source_system=event.source_system, data_source_id=data_source_id,
        )
        db.add(row)
    else:
        if event.event_timestamp < row.last_event_at:
            return None
        row.state_version += 1
        row.event_count += 1
        row.last_event_at = event.event_timestamp
        row.last_received_at = received_at
        row.payload = live
        row.source_system = event.source_system
        row.data_source_id = data_source_id or row.data_source_id
    db.flush()
    _publish_after_commit(db, organization_id, asset_id)
    return row


def _publish_after_commit(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID) -> None:
    """Subscribers must never see state that the database does not hold: publish only once the transaction commits.
    Several events for one asset in one transaction collapse into a single publication of the latest state."""
    pending = db.info.setdefault("_live_pending", set())
    pending.add((organization_id, asset_id))
    if db.info.get("_live_listener"):
        return
    db.info["_live_listener"] = True

    def _after_commit(session: Session) -> None:
        todo = session.info.pop("_live_pending", set())
        session.info["_live_listener"] = False
        for org, aid in todo:
            try:
                from app.db.session import SessionLocal

                with SessionLocal() as s:
                    state = get_drone_state(s, organization_id=org, asset_id=aid)
                broker.publish(org, "state", state.model_dump(mode="json", by_alias=True))
            except Exception as exc:  # noqa: BLE001 -- streaming is best-effort; the database already has the data
                log.warning("live.publish_failed", error=type(exc).__name__)

    sa_event.listen(db, "after_commit", _after_commit, once=True)


# ------------------------------------------------------------------------------------------------- read path
def _device_for(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID) -> EdgeDevice | None:
    return db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id, EdgeDevice.asset_id == asset_id,
            EdgeDevice.status != "REVOKED",
        ).order_by(EdgeDevice.last_heartbeat_at.desc().nullslast()).limit(1)
    ).scalar_one_or_none()


def _build(row: DroneLiveState | None, asset: Asset, device: EdgeDevice | None, now: datetime) -> LiveStateV1:
    payload = (row.payload if row else None) or {}
    ident = payload.get("identity") or {}
    connectivity = "UNKNOWN"
    if device is not None:
        connectivity = device_auth_service.connectivity_status(device, now)["connectivity"]
    body: dict[str, Any] = {g: payload[g] for g in _GROUPS if g in payload}
    return LiveStateV1.model_validate({
        "schema": SCHEMA_VERSION,
        "identity": LiveIdentityV1(
            asset_id=asset.id, device_id=device.device_id if device else (row.device_id if row else None),
            data_source_id=row.data_source_id if row else None,
            source_system=row.source_system if row else None, source_asset_id=ident.get("source_asset_id"),
        ).model_dump(),
        "state_version": row.state_version if row else 0,
        "observed_at": row.last_event_at if row else None,
        "received_at": row.last_received_at if row else None,
        "freshness": compute_freshness(row.last_received_at if row else None, now).model_dump(),
        "connectivity": connectivity,
        "status_texts": payload.get("status_texts", []),
        "provenance": {
            "source_system": row.source_system if row else None,
            "last_trigger": payload.get("trigger"),
            "event_count": row.event_count if row else 0,
        },
        **body,
    })


def _drone_asset(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    asset = db.execute(
        select(Asset).where(
            Asset.id == asset_id, Asset.organization_id == organization_id,
            Asset.asset_type == AssetType.DRONE.value, Asset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Drone not found")
    return asset


def get_drone_state(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> LiveStateV1:
    asset = _drone_asset(db, organization_id, asset_id)
    row = db.get(DroneLiveState, asset_id)
    if row is not None and row.organization_id != organization_id:
        row = None
    return _build(row, asset, _device_for(db, organization_id, asset_id), datetime.now(UTC))


def get_fleet_state(db: Session, *, organization_id: uuid.UUID) -> list[LiveStateV1]:
    """Every non-deleted drone of the tenant, including ones that never sent data (freshness NO_DATA)."""
    now = datetime.now(UTC)
    assets = db.execute(
        select(Asset).where(
            Asset.organization_id == organization_id, Asset.asset_type == AssetType.DRONE.value,
            Asset.deleted_at.is_(None),
        ).order_by(Asset.registration, Asset.id)
    ).scalars().all()
    rows = {
        r.asset_id: r for r in db.execute(
            select(DroneLiveState).where(DroneLiveState.organization_id == organization_id)
        ).scalars()
    }
    devices: dict[uuid.UUID, EdgeDevice] = {}
    for d in db.execute(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id, EdgeDevice.asset_id.is_not(None),
            EdgeDevice.status != "REVOKED",
        ).order_by(EdgeDevice.last_heartbeat_at.asc().nullsfirst())
    ).scalars():
        devices[d.asset_id] = d  # most recently heard-from device wins
    return [_build(rows.get(a.id), a, devices.get(a.id), now) for a in assets]
