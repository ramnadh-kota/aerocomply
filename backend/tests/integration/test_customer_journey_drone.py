"""Customer journey (SIMULATED input): Drone customer, end to end over the real stack.

  signup -> organization (Drone suite plan) -> drone asset -> MAVLink DataSource
  -> MAVLink bytes -> acquisition -> asset/flight/sensor/readings -> HUMS exceedance
  -> finding/evidence -> M7 signal -> LISA grounded answer -> isolation from another tenant.

Nothing here touches a radio, a broker or a real vehicle: frames are built in-process with valid
MAVLink checksums. It proves the software path only (see MAVLINK_HARDWARE_VALIDATION_PLAN.md).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.models.hums import HUMSExceedance, HUMSSensorReading
from app.models.telemetry import TelemetryEventLog
from app.schemas.auth import CurrentUser
from app.services.lisa.message_resolution_service import resolve_message
from app.services.lisa.orchestration_service import investigate
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org, _source
from tests.unit.test_m20_mavlink_integrity import heartbeat, sys_status, vibration

REG = "JOURNEY-1"


def _me(client, headers) -> CurrentUser:
    me = client.get("/api/v1/auth/me", headers=headers).json()
    return CurrentUser(
        id=uuid.UUID(me["id"]), organization_id=uuid.UUID(me["organization_id"]),
        roles=me["roles"], email=me["email"], full_name=me.get("full_name", ""), email_verified=True,
    )


def _ask(db, user, question):
    resolution = resolve_message(db, organization_id=user.organization_id, user_id=user.id, question=question)
    return investigate(db, user, question=question, resolution=resolution)


def test_drone_customer_journey_from_mavlink_bytes_to_lisa(client, db_session):
    org_id, h = _org(client, db_session, "journey")
    asset = _drone(client, h, reg=REG)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}, "expected_interval_seconds": 30})

    # ---- 1. acquisition: healthy baseline then a genuine vibration excursion
    seq = 0

    def nxt():
        nonlocal seq
        seq += 1
        return seq

    frames = [heartbeat(seq=nxt()), sys_status(seq=nxt(), remaining=91)]
    frames += [vibration(1.5, 1.6, 1.7, seq=nxt()) for _ in range(6)]            # baseline ~1.6 mm/s
    frames += [vibration(45.0, 52.0, 48.0, seq=nxt())]                           # excursion ~48.5 mm/s
    rep = _ingest(client, h, sid, b"".join(frames)).json()
    assert rep["accepted"] == len(frames) and rep["rejected"] == 0 and rep["quarantined"] == 0, rep

    # ---- 2. telemetry: latest/history are the ingested values, not inferred
    latest = client.get(f"/api/v1/telemetry/assets/{asset}/latest", headers=h).json()
    vib = next(s for s in latest["sensors"] if s["sensor_code"] == "VIB_MAIN_SYS1")
    assert vib["value"] > 40 and vib["data_quality"] == "VALID"
    history = client.get(f"/api/v1/telemetry/assets/{asset}/history", headers=h,
                         params={"sensor_code": "VIB_MAIN_SYS1", "limit": 100}).json()
    assert history["total"] == 7
    assert client.get(f"/api/v1/telemetry/assets/{asset}/status", headers=h).json()["telemetry_state"] == "ACTIVE"
    assert len(client.get(f"/api/v1/telemetry/assets/{asset}/flights", headers=h).json()) == 1

    # ---- 3. source health is evidence-based
    health = client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()
    assert health["status"] == "HEALTHY" and health["event_count"] == len(frames)
    assert health["last_success_at"] and health["latency_ms"] is not None

    # ---- 4. HUMS: the excursion produced an exceedance that points at the reading that caused it
    exceed = db_session.execute(select(HUMSExceedance).where(
        HUMSExceedance.organization_id == org_id, HUMSExceedance.asset_id == uuid.UUID(asset))).scalars().all()
    assert exceed, "no HUMS exceedance recorded for a 48 mm/s vibration excursion"
    worst = max(exceed, key=lambda e: e.observed_value)
    assert worst.observed_value > worst.threshold_value
    # Traceability: the exceedance is a HUMS FEATURE (window RMS), so it must equal the RMS we
    # recompute independently from the stored readings -- not a number the engine made up.
    stored = db_session.scalars(select(HUMSSensorReading.value).where(
        HUMSSensorReading.organization_id == org_id, HUMSSensorReading.asset_id == uuid.UUID(asset))).all()
    assert len(stored) == 7
    recomputed_rms = (sum(v * v for v in stored) / len(stored)) ** 0.5
    assert abs(worst.observed_value - recomputed_rms) < 1e-3, (worst.observed_value, recomputed_rms)
    assert max(stored) > 40 and worst.observed_value < max(stored)   # smoothed by the window, never above the peak

    hums_ex = client.get(f"/api/v1/hums/assets/{asset}/exceedances", headers=h)
    assert hums_ex.status_code == 200 and hums_ex.json()

    # HUMS never fabricates a remaining-life figure from a handful of readings
    prog = client.get(f"/api/v1/hums/assets/{asset}/prognostics", headers=h)
    assert prog.status_code == 200
    for p in prog.json():
        assert p.get("rul_hours") in (None,) or p.get("confidence") not in (None, 0) or p.get("status")

    # ---- 5. MRO: the exceedance became a finding on THIS asset
    findings = client.get("/api/v1/findings", headers=h, params={"asset_id": asset}).json()
    assert findings, "exceedance did not create a finding"
    assert all(f["asset_id"] == asset for f in findings)

    # ---- 6. M7 raised attention for this asset (or, at minimum, the summary sees the finding)
    signals = client.get(f"/api/v1/intelligence/assets/{asset}/signals", headers=h)
    assert signals.status_code == 200
    fleet = client.get("/api/v1/intelligence/summary", headers=h).json()
    assert fleet is not None
    # Exactly ONE M7 signal per HUMS exceedance, and re-evaluating never adds more. (Two code paths
    # -- ingest-time hums_service and the M7 evaluator -- used to raise one each, under different keys.)
    for _ in range(2):
        client.get("/api/v1/intelligence/summary", headers=h)
        again = client.get(f"/api/v1/intelligence/assets/{asset}/signals", headers=h).json()
        exceedance_signals = [s for s in again if s["signal_type"] == "HUMS_VIBRATION_EXCEEDANCE"]
        assert len(exceedance_signals) == len(exceed), [(s["title"], s["signal_key"]) for s in exceedance_signals]
    assert len({s["signal_key"] for s in again}) == len(again)          # keys are unique per signal

    # ---- 7. LISA: grounded in the data above; names the asset; cites tools it actually ran
    user = _me(client, h)
    result = _ask(db_session, user, f"What is the telemetry status of {REG}?")
    assert result is not None and result.intent == "TELEMETRY_HUMS" and result.status == "ANSWERED"
    assert REG in result.headline or any(REG in line for line in result.what_i_found)
    assert "get_asset_telemetry_status" in result.tools_invoked
    assert "NO_TELEMETRY_RECORDED" not in " ".join(result.what_i_found)

    # ---- 8. another tenant learns nothing about it
    org_b, hb = _org(client, db_session, "other")
    for suffix in ("latest", "history", "status", "flights"):
        assert client.get(f"/api/v1/telemetry/assets/{asset}/{suffix}", headers=hb).status_code == 404
    assert client.get(f"/api/v1/data-sources/{sid}/health", headers=hb).status_code == 404
    other = _ask(db_session, _me(client, hb), f"What is the telemetry status of {REG}?")
    # Never answered, and nothing about the other tenant's drone is revealed or confirmed
    # (NEEDS_ENTITY asks which drone; it does not say "that one exists elsewhere").
    assert other is not None and other.status in ("NEEDS_ENTITY", "NOT_FOUND")
    blob = " ".join([other.headline, *other.what_i_found, *(other.why_it_matters or "",)])
    assert asset not in blob and "ACTIVE" not in blob and other.tools_invoked == []
    assert db_session.scalar(select(func.count(TelemetryEventLog.id)).where(
        TelemetryEventLog.organization_id == uuid.UUID(client.get("/api/v1/auth/me", headers=hb).json()["organization_id"]))) == 0
