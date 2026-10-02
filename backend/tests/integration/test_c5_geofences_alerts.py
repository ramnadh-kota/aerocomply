"""C5: geofence configuration, live evaluation (entry / exit / proximity / debounce / hysteresis / bad GPS), the alert
lifecycle on top of M7, battery and telemetry-loss rules, tenant isolation and the snapshot contract."""
import itertools
import json
import math
import struct
import uuid
from datetime import UTC, datetime, timedelta

from app.core import metrics
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org, _source
from tests.unit.test_m20_mavlink_integrity import frame_v2, heartbeat, sys_status

LAT, LON = 10.0, 77.0
M_PER_DEG_LAT = 111_194.9
_seq = itertools.count(1)


def pos(m_east: float, *, fix=3, hdop_cs=120, rel_mm=None, lat=LAT):
    """ONE position observation `m_east` metres east of the fence centre: a GPS_RAW_INT (fix quality + MSL altitude).
    With `rel_mm` a GLOBAL_POSITION_INT (home-relative altitude) follows, which counts as a second observation."""
    lon = LON + m_east / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    la, lo = int(lat * 1e7), int(lon * 1e7)
    out = frame_v2(24, struct.pack("<QiiiHHHHBB", 1, la, lo, 100_000, hdop_cs, 200, 0, 0, fix, 10), seq=next(_seq) % 256)
    if rel_mm is not None:
        out += frame_v2(33, struct.pack("<IiiiihhhH", 1, la, lo, 100_000, rel_mm, 0, 0, 0, 0), seq=next(_seq) % 256)
    return out


def hb():
    return heartbeat(seq=next(_seq) % 256)


def batt(pct):
    return sys_status(remaining=pct, seq=next(_seq) % 256)


def _setup(client, db_session, tag):
    org_id, h = _org(client, db_session, tag)
    asset = _drone(client, h)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    return uuid.UUID(str(org_id)), h, asset, sid


def _fence(client, h, **kw):
    body = {"name": "Airport", "kind": "RESTRICTED", "geometry_type": "CIRCLE",
            "geometry": {"center": {"lat": LAT, "lon": LON}, "radius_m": 200}, "severity": "HIGH",
            "proximity_buffer_m": 100, "boundary_tolerance_m": 5, "confirm_count": 2, **kw}
    r = client.post("/api/v1/geofences", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _alerts(client, h, **params):
    r = client.get("/api/v1/live/alerts", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()["alerts"]


def _types(alerts):
    return sorted(a["alert_type"] for a in alerts)


# ---------------------------------------------------------------------------------------- configuration
def test_geofence_crud_validation_versioning_and_isolation(client, db_session):
    org1, h1, asset, _ = _setup(client, db_session, "c5cfg1")
    _, h2, _, _ = _setup(client, db_session, "c5cfg2")
    g = _fence(client, h1, asset_ids=[asset])
    assert g["version"] == 1 and g["organization_id"] == str(org1)
    assert "not authoritative" in g["advisory_notice"].lower()
    assert g["asset_ids"] == [asset]

    # invalid geometry / unsupported config -> 422 with a clear code
    for bad in ({"geometry": {"center": {"lat": 95, "lon": 0}, "radius_m": 10}},
                {"geometry_type": "POLYGON", "geometry": {"ring": [[0, 0], [1, 1]]}},
                {"alt_min_m": 50, "alt_max_m": 10}):
        r = client.post("/api/v1/geofences", headers=h1, json={
            "name": "x", "kind": "RESTRICTED", "geometry_type": "CIRCLE",
            "geometry": {"center": {"lat": 1, "lon": 1}, "radius_m": 10}, **bad})
        assert r.status_code in (400, 422), r.text
    # another tenant's drone cannot be referenced; same answer as for a non-existent one
    foreign = _drone(client, h2)
    r = client.post("/api/v1/geofences", headers=h1, json={
        "name": "x", "kind": "CAUTION", "geometry_type": "CIRCLE",
        "geometry": {"center": {"lat": 1, "lon": 1}, "radius_m": 10}, "asset_ids": [foreign]})
    assert r.status_code == 422
    # tenant cannot be injected
    r = client.post("/api/v1/geofences", headers=h1, json={
        "name": "x", "kind": "CAUTION", "geometry_type": "CIRCLE", "organization_id": str(uuid.uuid4()),
        "geometry": {"center": {"lat": 1, "lon": 1}, "radius_m": 10}})
    assert r.status_code == 422

    # update bumps the version, a no-op does not; history is immutable and audited
    gid = g["id"]
    r = client.patch(f"/api/v1/geofences/{gid}", headers=h1, json={"severity": "CRITICAL", "reason": "airport expansion"})
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["severity"] == "CRITICAL"
    assert client.patch(f"/api/v1/geofences/{gid}", headers=h1, json={"severity": "CRITICAL"}).json()["version"] == 2
    r = client.post(f"/api/v1/geofences/{gid}/deactivate", headers=h1, json={"reason": "closed"})
    assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["version"] == 3
    hist = client.get(f"/api/v1/geofences/{gid}/history", headers=h1).json()
    assert [(v["version"], v["change_type"]) for v in hist] == [(3, "DEACTIVATED"), (2, "UPDATED"), (1, "CREATED")]
    assert hist[0]["snapshot"]["is_active"] is False and hist[2]["snapshot"]["severity"] == "HIGH"
    from app.models.audit_event import AuditEvent

    actions = {e.action for e in db_session.query(AuditEvent).filter_by(entity_id=uuid.UUID(gid)).all()}
    assert {"geofence.created", "geofence.updated", "geofence.deactivated"} <= actions

    assert gid not in [x["id"] for x in client.get("/api/v1/geofences", headers=h1).json()]
    assert gid in [x["id"] for x in client.get("/api/v1/geofences?include_inactive=true", headers=h1).json()]
    # isolation: org 2 sees / changes nothing of org 1
    assert client.get(f"/api/v1/geofences/{gid}", headers=h2).status_code == 404
    assert client.patch(f"/api/v1/geofences/{gid}", headers=h2, json={"name": "hijack"}).status_code == 404
    assert client.get(f"/api/v1/geofences/{gid}/history", headers=h2).status_code == 404
    assert client.get("/api/v1/geofences").status_code in (401, 403)
    assert client.post("/api/v1/geofences", json={}).status_code in (401, 403)


# ------------------------------------------------------------------------------------------- evaluation
def test_entry_exit_proximity_debounce_hysteresis_and_new_episode(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5eval")
    g = _fence(client, h)
    ing = lambda body: _ingest(client, h, sid, body).status_code == 200  # noqa: E731
    assert ing(hb() + pos(600))                                   # far away, armed
    assert _alerts(client, h) == []
    assert ing(pos(600) + pos(600))

    # 50 m outside the edge, inside the 100 m proximity buffer -> proximity (MEDIUM), needs 2 reliable updates
    assert ing(pos(250))
    assert _alerts(client, h) == []                               # first outside observation: still debouncing
    assert ing(pos(250))
    (prox,) = _alerts(client, h)
    assert prox["alert_type"] == "GEOFENCE_PROXIMITY" and prox["severity"] == "MEDIUM"
    assert prox["geofence_id"] == g["id"] and prox["asset_id"] == asset
    assert prox["rule"]["rule_version"] == 1 and prox["rule"]["episode"] == 1
    assert prox["evidence"] and prox["provenance"]["state_version"] >= 1

    # a single inside blip is suppressed (debounce) and does not raise a breach
    suppressed_before = metrics.LIVE_ALERTS_SUPPRESSED.value(rule="geofence_debounce")
    assert ing(pos(150))
    assert ing(pos(250))
    assert metrics.LIVE_ALERTS_SUPPRESSED.value(rule="geofence_debounce") > suppressed_before
    assert "GEOFENCE_BREACH" not in _types(_alerts(client, h))

    # two consecutive inside updates -> breach (HIGH), proximity alert closes itself
    assert ing(pos(150)) and ing(pos(140))
    alerts = _alerts(client, h)
    assert _types(alerts) == ["GEOFENCE_BREACH"]
    (breach,) = alerts
    assert breach["severity"] == "HIGH" and breach["condition_active"] is True
    assert breach["provenance"]["geofence_version"] == 1
    assert breach["provenance"]["position"]["position_quality"] == "ok"
    resolved = _alerts(client, h, status="RESOLVED")
    assert [a["alert_type"] for a in resolved] == ["GEOFENCE_PROXIMITY"] and resolved[0]["resolved_by_user_id"] is None

    # further inside updates never duplicate the alert
    for _ in range(5):
        assert ing(pos(120))
    assert len(_alerts(client, h)) == 1

    # boundary jitter just outside the edge (3 m < 5 m tolerance) keeps the drone INSIDE: no clearing, no flapping
    for _ in range(4):
        assert ing(pos(203))
    assert _alerts(client, h)[0]["condition_active"] is True

    # clearly outside (15 m) for 2 updates -> condition clears; the breach stays OPEN for the operator
    assert ing(pos(215)) and ing(pos(216))
    (b,) = _alerts(client, h, alert_type="GEOFENCE_BREACH")
    assert b["condition_active"] is False and b["status"] == "OPEN" and b["cleared_at"]

    # a later re-entry is a NEW alert (new episode), not a revival of the old one
    assert ing(pos(150)) and ing(pos(150))
    breaches = _alerts(client, h, alert_type="GEOFENCE_BREACH")
    assert len(breaches) == 2
    assert sorted(a["rule"]["episode"] for a in breaches) == [1, 2]
    # no live alert type is ever mis-labelled: M7 listing (Literal-validated) must serve them too
    r = client.get("/api/v1/intelligence/signals", headers=h)
    assert r.status_code == 200
    assert "GEOFENCE_BREACH" in {s["signal_type"] for s in r.json()}


def test_unreliable_position_never_changes_state(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5gps")
    _fence(client, h)
    ing = lambda body: _ingest(client, h, sid, body).status_code == 200  # noqa: E731
    assert ing(hb() + pos(600) + pos(600))
    before = {r: metrics.LIVE_EVAL_SKIPPED.value(reason=r) for r in ("poor_fix", "poor_hdop")}
    for _ in range(4):
        assert ing(pos(100, fix=2))            # 2D fix, "inside" -> must be ignored
    for _ in range(4):
        assert ing(pos(100, hdop_cs=900))      # HDOP 9.0 > 5.0 -> must be ignored
    assert _alerts(client, h) == []
    assert metrics.LIVE_EVAL_SKIPPED.value(reason="poor_fix") > before["poor_fix"]
    assert metrics.LIVE_EVAL_SKIPPED.value(reason="poor_hdop") > before["poor_hdop"]
    # a poor fix while breached must not clear the alert either
    assert ing(pos(100)) and ing(pos(100))
    assert _types(_alerts(client, h)) == ["GEOFENCE_BREACH"]
    for _ in range(4):
        assert ing(pos(900, fix=2))
    assert _alerts(client, h)[0]["condition_active"] is True


def test_stale_position_is_not_used(client, db_session):
    """A position older than live_position_max_age_s (other messages keep the state 'fresh') gives no decision."""
    from app.core.config import get_settings
    from app.services import live_alert_service as las

    old = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
    payload = {"position": {"lat": LAT, "lon": LON, "observed_at": old, "gps_fix_type": 3}}
    assert las.position_quality(payload, datetime.now(UTC)) == (None, "stale_position")
    ok = {"position": {"lat": LAT, "lon": LON, "observed_at": datetime.now(UTC).isoformat(), "gps_fix_type": 3}}
    assert las.position_quality(ok, datetime.now(UTC))[1] == "ok"
    unknown_fix = {"position": {"lat": LAT, "lon": LON, "observed_at": datetime.now(UTC).isoformat()}}
    assert las.position_quality(unknown_fix, datetime.now(UTC))[1] == "unverified_fix"
    assert las.position_quality({"position": {"lat": 0.0, "lon": 0.0, "observed_at": ok["position"]["observed_at"]}},
                                datetime.now(UTC))[0] is None
    assert get_settings().live_position_max_age_s > 0


def test_operating_area_leaving_is_the_breach_and_altitude_limits(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5area")
    _fence(client, h, name="Field", kind="OPERATING_AREA", severity="MEDIUM", proximity_buffer_m=0, alt_max_m=120,
           altitude_reference="HOME_RELATIVE")
    ing = lambda body: _ingest(client, h, sid, body).status_code == 200  # noqa: E731
    skipped = metrics.LIVE_EVAL_SKIPPED.value(reason="no_altitude")
    assert ing(hb() + pos(50) + pos(50) + pos(50))                 # home-relative altitude never reported => no decision
    assert _alerts(client, h) == []
    assert metrics.LIVE_EVAL_SKIPPED.value(reason="no_altitude") > skipped
    assert ing(pos(50, rel_mm=20_000) + pos(50, rel_mm=20_000))    # inside, 20 m < 120 m ceiling
    assert _alerts(client, h) == []
    assert ing(pos(50, rel_mm=150_000) + pos(50, rel_mm=150_000))  # inside horizontally, above the ceiling => outside
    (a,) = _alerts(client, h)
    assert a["alert_type"] == "GEOFENCE_BREACH" and a["severity"] == "MEDIUM"


def test_deactivated_geofence_closes_alert_and_resets_state(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5deact")
    g = _fence(client, h)
    ing = lambda body: _ingest(client, h, sid, body).status_code == 200  # noqa: E731
    assert ing(hb() + pos(100) + pos(100) + pos(100))
    assert _types(_alerts(client, h)) == ["GEOFENCE_BREACH"]
    assert client.post(f"/api/v1/geofences/{g['id']}/deactivate", headers=h, json={}).status_code == 200
    assert ing(pos(100) + pos(100))
    (b,) = _alerts(client, h, alert_type="GEOFENCE_BREACH")
    assert b["condition_active"] is False and "no longer applies" in b["cleared_reason"] and b["status"] == "OPEN"
    # reactivated while the drone is OUTSIDE: a stale INSIDE must not produce an instant breach
    client.patch(f"/api/v1/geofences/{g['id']}", headers=h, json={"is_active": True})
    assert ing(pos(900))
    assert len(_alerts(client, h, alert_type="GEOFENCE_BREACH")) == 1


# ---------------------------------------------------------------------------------------------- lifecycle
def test_alert_lifecycle_acknowledge_resolve_reopen_and_isolation(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5life")
    _, h2, _, _ = _setup(client, db_session, "c5life2")
    _fence(client, h)
    assert _ingest(client, h, sid, hb() + pos(100) + pos(100) + pos(100)).status_code == 200
    (a,) = _alerts(client, h)
    aid = a["id"]
    url = f"/api/v1/live/alerts/{aid}"

    assert client.post(f"{url}/acknowledge", headers=h2).status_code == 404          # foreign tenant
    assert client.get(url, headers=h2).status_code == 404
    assert client.post(f"{url}/acknowledge").status_code in (401, 403)
    r = client.post(f"{url}/acknowledge", headers=h, json={})
    assert r.status_code == 200 and r.json()["status"] == "ACKNOWLEDGED" and r.json()["acknowledged_by_user_id"]
    assert client.post(f"{url}/reopen", headers=h).status_code == 409                # only closed alerts reopen
    assert client.post(f"{url}/resolve", headers=h, json={}).status_code == 409      # a note is required
    r = client.post(f"{url}/resolve", headers=h, json={"notes": "drone landed, zone cleared"})
    assert r.status_code == 200 and r.json()["status"] == "RESOLVED"
    assert _alerts(client, h) == []                                                  # closed alerts leave the active list
    assert [x["id"] for x in _alerts(client, h, status="RESOLVED")] == [aid]
    assert client.post(f"{url}/acknowledge", headers=h).status_code == 409           # no transition out of RESOLVED
    r = client.post(f"{url}/reopen", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "OPEN" and r.json()["reopen_count"] == 1
    assert r.json()["resolved_at"] is None
    assert client.post(f"{url}/dismiss", headers=h, json={"notes": "test zone"}).json()["status"] == "DISMISSED"
    assert client.post(f"{url}/reopen", headers=h).json()["reopen_count"] == 2
    # the full history is in the audit trail
    from app.models.audit_event import AuditEvent

    acts = [e.action for e in db_session.query(AuditEvent).filter_by(entity_id=uuid.UUID(aid)).all()]
    for expected in ("live_alert.raised", "proactive_signal.acknowledge", "proactive_signal.resolve",
                     "proactive_signal.reopen", "proactive_signal.dismiss"):
        assert expected in acts, acts
    # non-live M7 signals are not reachable through the live API
    assert client.get(f"/api/v1/live/alerts/{uuid.uuid4()}", headers=h).status_code == 404


# ----------------------------------------------------------------------------------------- battery & loss
def test_low_battery_debounce_escalation_and_auto_resolve(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5bat")
    ing = lambda body: _ingest(client, h, sid, body).status_code == 200  # noqa: E731
    assert ing(hb() + batt(80))
    assert ing(batt(20))
    assert _alerts(client, h) == []                       # one low reading is not enough
    assert ing(batt(19))
    (a,) = _alerts(client, h)
    assert a["alert_type"] == "LIVE_LOW_BATTERY" and a["severity"] == "MEDIUM" and a["rule"]["episode"] == 1
    assert ing(batt(18)) and ing(batt(17))
    assert len(_alerts(client, h)) == 1                   # dedup while low
    assert ing(batt(12))
    (a,) = _alerts(client, h)
    assert a["severity"] == "CRITICAL"                    # escalated in place, same alert
    assert ing(batt(28))                                  # inside the hysteresis margin (< 25 + 5): stays active
    assert _types(_alerts(client, h)) == ["LIVE_LOW_BATTERY"]
    assert ing(batt(60))
    assert _alerts(client, h) == []
    (done,) = _alerts(client, h, status="RESOLVED")
    assert done["resolved_by_user_id"] is None and "Auto-resolved" in done["resolution_notes"]


def test_low_battery_on_the_ground_is_not_an_in_flight_alert(client, db_session):
    _, h, asset, sid = _setup(client, db_session, "c5batground")
    disarmed = frame_v2(0, struct.pack("<IBBBBB", 3, 2, 3, 1, 3, 3), seq=next(_seq) % 256)
    assert _ingest(client, h, sid, disarmed + batt(5) + batt(4) + batt(3)).status_code == 200
    assert _alerts(client, h) == []


def test_telemetry_loss_sweep_is_idempotent_and_recovers(client, db_session):
    from app.services import live_alert_service as las

    org_id, h, asset, sid = _setup(client, db_session, "c5loss")
    assert _ingest(client, h, sid, hb() + batt(70)).status_code == 200
    now = datetime.now(UTC)
    assert las.sweep_telemetry_loss(db_session, organization_id=org_id, now=now)["raised"] == 0   # still fresh
    later = now + timedelta(seconds=120)
    assert las.sweep_telemetry_loss(db_session, organization_id=org_id, now=later)["raised"] == 1
    assert las.sweep_telemetry_loss(db_session, organization_id=org_id, now=later)["raised"] == 0  # idempotent
    db_session.commit()
    (a,) = _alerts(client, h)
    assert a["alert_type"] == "LIVE_TELEMETRY_LOSS" and a["severity"] == "HIGH"
    assert a["provenance"]["last_received_at"] and a["evidence"][0]["metric"] == "seconds_since_last_report"
    # telemetry returns -> auto-resolved, a later silence is a new episode
    assert _ingest(client, h, sid, hb() + batt(70)).status_code == 200
    assert _alerts(client, h) == []
    assert _alerts(client, h, status="RESOLVED")[0]["alert_type"] == "LIVE_TELEMETRY_LOSS"
    assert las.sweep_telemetry_loss(db_session, organization_id=org_id, now=datetime.now(UTC) + timedelta(seconds=300))["raised"] == 1


def test_disarmed_silent_drone_is_offline_not_an_alert(client, db_session):
    from app.services import live_alert_service as las

    org_id, h, asset, sid = _setup(client, db_session, "c5off")
    disarmed = frame_v2(0, struct.pack("<IBBBBB", 3, 2, 3, 1, 3, 3), seq=next(_seq) % 256)
    assert _ingest(client, h, sid, disarmed).status_code == 200
    assert las.sweep_telemetry_loss(db_session, organization_id=org_id, now=datetime.now(UTC) + timedelta(hours=1))["raised"] == 0


# ------------------------------------------------------------------------------------- snapshot contract
def test_fleet_and_stream_snapshot_expose_active_alerts(client, db_session):
    import asyncio
    from types import SimpleNamespace

    from app.api.v1 import live as live_mod

    org_id, h, asset, sid = _setup(client, db_session, "c5snap")
    _, h2, _, _ = _setup(client, db_session, "c5snap2")
    _fence(client, h)
    assert _ingest(client, h, sid, hb() + pos(100) + pos(100) + pos(100)).status_code == 200
    fleet = client.get("/api/v1/live/fleet", headers=h).json()
    assert [a["alert_type"] for a in fleet["alerts"]] == ["GEOFENCE_BREACH"]
    assert client.get("/api/v1/live/fleet", headers=h2).json()["alerts"] == []

    class _Req:
        async def is_disconnected(self):
            return False

    async def first_chunk(last_event_id=None):
        resp = await live_mod.live_stream(request=_Req(), db=db_session,
                                          current_user=SimpleNamespace(organization_id=org_id), last_event_id=last_event_id)
        async for chunk in resp.body_iterator:
            await resp.body_iterator.aclose()
            return chunk

    chunk = asyncio.run(first_chunk())
    assert "event: snapshot" in chunk
    data = json.loads(chunk.split("data: ", 1)[1])
    assert data["alerts"][0]["alert_type"] == "GEOFENCE_BREACH" and data["alerts"][0]["schema"] == "kota.drone.live_alert.v1"
    assert "event: resync_required" in asyncio.run(first_chunk("deadbeef:9"))   # unusable cursor => client refetches
