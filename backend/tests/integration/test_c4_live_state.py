"""C4: latest live state (single writer from the acquisition pipeline), REST snapshots, tenant isolation, SSE contract."""
import json
import uuid

from sqlalchemy import select

from app.models.drone_live_state import DroneLiveState
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org, _source
from tests.unit.test_c3_mavlink_live_state import mission_current, reached, statustext
from tests.unit.test_m20_mavlink_integrity import heartbeat, sys_status


def _setup(client, db_session, tag="c4"):
    org_id, h = _org(client, db_session, tag)
    a1 = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": a1}})
    return org_id, h, a1, sid


def test_ingest_populates_latest_state_and_fleet_includes_silent_drones(client, db_session):
    org_id, h, a1, sid = _setup(client, db_session)
    silent = _drone(client, h)
    stream = heartbeat(seq=1) + sys_status(seq=2) + mission_current(seq=3) + reached(item=2, seq=4) + statustext(b"Hello", seq=5)
    assert _ingest(client, h, sid, stream).json()["accepted"] == 5

    one = client.get(f"/api/v1/live/drones/{a1}", headers=h)
    assert one.status_code == 200, one.text
    s = one.json()
    assert s["schema"] == "kota.drone.live_state.v1" and s["state_version"] == 5
    assert s["freshness"]["state"] == "FRESH"
    assert s["battery"]["remaining_pct"] == 87 and s["mode"]["armed"] is True
    assert s["mission"]["current_seq"] == 3 and s["mission"]["last_reached_seq"] == 2
    assert s["status_texts"][0]["text"] == "Hello" and s["position"]["lat"] is None

    fleet = client.get("/api/v1/live/fleet", headers=h).json()
    by_id = {d["identity"]["asset_id"]: d for d in fleet["drones"]}
    assert by_id[silent]["freshness"]["state"] == "NO_DATA" and by_id[silent]["state_version"] == 0
    assert by_id[a1]["freshness"]["state"] == "FRESH" and fleet["cursor"]
    assert db_session.scalar(select(DroneLiveState).where(DroneLiveState.asset_id == uuid.UUID(a1))).event_count == 5


def test_out_of_order_event_does_not_overwrite_newer_state(client, db_session):
    from datetime import UTC, datetime, timedelta

    from app.schemas.telemetry import NormalizedTelemetryEvent
    from app.services import live_state_service

    org_id, h, a1, sid = _setup(client, db_session, "c4o")
    assert _ingest(client, h, sid, heartbeat(seq=1) + sys_status(seq=2)).json()["accepted"] == 2
    row = db_session.scalar(select(DroneLiveState).where(DroneLiveState.asset_id == uuid.UUID(a1)))
    old = NormalizedTelemetryEvent(
        source_system="MAVLINK", source_event_id="old", source_asset_id="x", event_type="REALTIME_TELEMETRY",
        event_timestamp=row.last_event_at - timedelta(seconds=30), raw_metadata={"live_state": {"stale": True}})
    assert live_state_service.apply_event(db_session, organization_id=org_id, asset_id=uuid.UUID(a1), event=old) is None
    assert "stale" not in db_session.scalar(select(DroneLiveState).where(DroneLiveState.asset_id == uuid.UUID(a1))).payload


def test_tenant_isolation_and_auth(client, db_session):
    _, h1, a1, sid = _setup(client, db_session, "c4a")
    _, h2, _a2, _ = _setup(client, db_session, "c4b")
    assert _ingest(client, h1, sid, heartbeat(seq=1)).json()["accepted"] == 1
    assert client.get(f"/api/v1/live/drones/{a1}", headers=h2).status_code == 404
    assert all(d["identity"]["asset_id"] != a1 for d in client.get("/api/v1/live/fleet", headers=h2).json()["drones"])
    assert client.get("/api/v1/live/fleet").status_code in (401, 403)
    assert client.get("/api/v1/live/stream").status_code in (401, 403)


def _drive_stream(live_mod, org_id, db_session, last_event_id=None, n_events=1):
    """Starlette's TestClient buffers whole responses, so an endless SSE stream cannot be read through it: call the
    route function and consume its body iterator directly."""
    import asyncio
    from types import SimpleNamespace

    class _Req:
        async def is_disconnected(self):
            return False

    async def run():
        resp = await live_mod.live_stream(
            request=_Req(), db=db_session, current_user=SimpleNamespace(organization_id=org_id),
            last_event_id=last_event_id,
        )
        out = []
        async for chunk in resp.body_iterator:
            out.append(chunk)
            if len(out) >= n_events:
                break
        await resp.body_iterator.aclose()
        return out

    return asyncio.run(run())


def test_sse_snapshot_and_resync(client, db_session):
    """The stream generator is driven directly: TestClient cannot close an endless SSE response."""
    import asyncio

    from app.api.v1 import live
    from app.schemas.auth import CurrentUser

    org_id, h, a1, sid = _setup(client, db_session, "c4s")
    _ingest(client, h, sid, heartbeat(seq=1))
    user = CurrentUser(id=uuid.uuid4(), organization_id=org_id, email="x@example.com", full_name="x", roles=["ORG_ADMIN"],
                       email_verified=True)

    class Req:
        async def is_disconnected(self):
            return False

    async def first(last_event_id):
        resp = await live.live_stream(Req(), db=db_session, current_user=user, last_event_id=last_event_id)
        assert resp.media_type == "text/event-stream"
        chunk = await asyncio.wait_for(resp.body_iterator.__anext__(), 5)
        await resp.body_iterator.aclose()
        lines = chunk.strip().splitlines()
        return lines[0], lines[1].split(": ", 1)[1], json.loads(lines[2].split(": ", 1)[1])

    id_line, ev, data = asyncio.run(first(None))
    assert ev == "snapshot" and id_line.startswith("id: ") and data["cursor"]
    assert [d["identity"]["asset_id"] for d in data["drones"]] == [a1]
    id_line, ev, data = asyncio.run(first("deadbeef:5"))
    assert ev == "resync_required"
