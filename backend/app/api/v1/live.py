"""C4: read-only live fleet state. REST snapshots plus one SSE stream (tenant from the JWT, never from the request).

Stream protocol (`GET /live/stream`): first event `snapshot` (full fleet + cursor in the SSE `id`), then `state` /
`heartbeat` events. Clients resume with `Last-Event-ID`; an unusable cursor yields `resync_required` and the client
re-fetches `/live/fleet`. Events are idempotent by (asset_id, state_version)."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.live_state import LiveStateV1
from app.services import live_state_service as svc

router = APIRouter(
    prefix="/live", tags=["live"],
    dependencies=[Depends(require_feature("flight_telemetry"))],
)

HEARTBEAT_SECONDS = 15.0


class LiveFleetResponse(BaseModel):
    cursor: str
    drones: list[LiveStateV1]


@router.get("/fleet", response_model=LiveFleetResponse, response_model_by_alias=True)
def live_fleet(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> LiveFleetResponse:
    cursor = svc.broker.cursor(current_user.organization_id)  # read BEFORE the snapshot: replay can only over-deliver
    return LiveFleetResponse(
        cursor=cursor, drones=svc.get_fleet_state(db, organization_id=current_user.organization_id)
    )


@router.get("/drones/{asset_id}", response_model=LiveStateV1, response_model_by_alias=True)
def live_drone(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> LiveStateV1:
    return svc.get_drone_state(db, organization_id=current_user.organization_id, asset_id=asset_id)


def _sse(type_: str, data: dict, event_id: str | None = None) -> str:
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {type_}\ndata: {json.dumps(data, default=str)}\n\n"


def _snapshot_sync(db: Session, organization_id: uuid.UUID) -> tuple[str, list[dict]]:
    cursor = svc.broker.cursor(organization_id)  # before the read: a replay may over-deliver, never miss
    drones = svc.get_fleet_state(db, organization_id=organization_id)
    db.rollback()  # release the request connection; the long-lived stream holds no database resources
    return cursor, [d.model_dump(mode="json", by_alias=True) for d in drones]


@router.get("/stream")
async def live_stream(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    org = current_user.organization_id
    snapshot = None if last_event_id else await run_in_threadpool(_snapshot_sync, db, org)
    if snapshot is None:
        db.rollback()

    async def gen() -> AsyncIterator[str]:
        sub = svc.broker.subscribe(org)
        try:
            backlog = None
            if last_event_id:
                backlog = svc.broker.replay_after(org, last_event_id)
                if backlog is None:
                    yield _sse("resync_required", {"reason": "cursor_unavailable"}, svc.broker.cursor(org))
                    backlog = []
            if snapshot is not None:
                cursor, drones = snapshot
                yield _sse("snapshot", {"cursor": cursor, "drones": drones}, cursor)
            last_n = 0
            for item in backlog or []:
                last_n = item["n"]
                yield _sse(item["type"], item["data"], item["id"])
            while True:
                if await request.is_disconnected():
                    return
                if sub.overflowed:
                    yield _sse("resync_required", {"reason": "slow_consumer"}, svc.broker.cursor(org))
                    return
                try:
                    item = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield _sse("heartbeat", {"cursor": svc.broker.cursor(org)})
                    continue
                if item["n"] <= last_n:
                    continue  # already delivered through the replay
                yield _sse(item["type"], item["data"], item["id"])
        finally:
            svc.broker.unsubscribe(sub)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
