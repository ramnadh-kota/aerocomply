"""Customer journeys (SIMULATED input) for the Helicopter and eVTOL suites, end to end over the real stack:

  suite plan -> organization + admin login -> airframe (+ details) -> components -> HUMS starter sensors
  -> CSV data source -> telemetry (baseline + excursion) -> HUMS exceedance -> finding -> M7 signal
  -> flight hours / cycles -> maintenance work order -> audit trail -> LISA -> isolation from other suites/tenants.

Nothing here touches a radio, broker or aircraft. It proves the software path, and that suite boundaries hold."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.hums import HUMSExceedance, HUMSSensor
from app.schemas.auth import CurrentUser
from app.services.ai.tools import execute_tool
from tests.integration.test_acquisition_pipeline import _csv, _ingest, _source
from tests.integration.test_customer_journeys_commercial import _customer, _plan

HELI_PLAN = ["helicopter_fleet_management", "flight_telemetry", "hums", "work_order_management", "lisa_ai_copilot",
             "predictive_maintenance"]
EVTOL_PLAN = ["evtol_fleet_management", "battery_analytics", "flight_telemetry", "hums", "work_order_management",
              "lisa_ai_copilot", "predictive_maintenance"]


def _user(client, h) -> CurrentUser:
    me = client.get("/api/v1/auth/me", headers=h).json()
    return CurrentUser(id=uuid.UUID(me["id"]), organization_id=uuid.UUID(me["organization_id"]), roles=me["roles"],
                       email=me["email"], full_name=me.get("full_name", ""), email_verified=True)


def _telemetry(reg, sensor, unit, values, start_minute=0):
    return _csv([{"asset_id": reg, "sensor_code": sensor, "value": str(v), "unit": unit,
                  "timestamp": f"2026-09-01T10:{start_minute + i:02d}:00Z"} for i, v in enumerate(values)])


@pytest.mark.parametrize("family,path,suite,plan,registration,detail,sensor", [
    ("helicopter", "helicopters", "HELICOPTER", HELI_PLAN, "VT-JH1",
     {"rotor_system": "SINGLE_MAIN_TAIL", "main_rotor_blade_count": 4, "engine_count": 2}, "MR-VIB"),
    ("evtol", "evtols", "EVTOL_AAM", EVTOL_PLAN, "VT-EV1",
     {"configuration": "LIFT_CRUISE", "propulsor_count": 4, "battery_nominal_energy_kwh": 100.0}, "PROP1-VIB"),
])
def test_airframe_customer_journey(client, db_session, family, path, suite, plan, registration, detail, sensor):
    org, _subs, h, _admin = _customer(client, db_session, [_plan(db_session, suite, plan)])
    base = f"/api/v1/{path}"

    # ---- 1. asset + configuration
    a = client.post(base, headers=h, json={"registration": registration, "manufacturer": "OEM", "model": "M1",
                                           "detail": detail})
    assert a.status_code == 201, a.text
    asset_id = a.json()["id"]
    for ctype, cname in (("MOTOR" if family == "evtol" else "ROTOR", "Primary propulsor"),):
        assert client.post(f"{base}/{asset_id}/components", headers=h,
                           json={"component_type": ctype, "name": cname}).status_code == 201
    tmpl = client.post(f"{base}/{asset_id}/hums/apply-template", headers=h).json()
    assert sensor in tmpl["created"]

    # ---- 2. acquisition: healthy baseline, then an excursion, through the normal pipeline
    sid = _source(client, h, "CSV_BATCH")
    values = [1.5, 1.6, 1.5, 1.7, 1.6, 1.5, 48.0, 52.0]
    rep = _ingest(client, h, sid, _telemetry(registration, sensor, "mm/s", values)).json()
    assert rep["accepted"] == len(values) and rep["rejected"] == 0 and rep["quarantined"] == 0, rep
    assert client.get(f"/api/v1/data-sources/{sid}/health", headers=h).json()["status"] == "HEALTHY"

    # ---- 3. HUMS: the template's sensor received the readings (no duplicate auto-created sensor)
    sensors = db_session.execute(select(HUMSSensor).where(
        HUMSSensor.organization_id == org.id, HUMSSensor.asset_id == uuid.UUID(asset_id),
        HUMSSensor.sensor_code == sensor)).scalars().all()
    assert len(sensors) == 1 and sensors[0].source == "IMPORTED"
    exceed = db_session.execute(select(HUMSExceedance).where(
        HUMSExceedance.organization_id == org.id, HUMSExceedance.asset_id == uuid.UUID(asset_id))).scalars().all()
    assert exceed and max(e.observed_value for e in exceed) > max(e.threshold_value for e in exceed)

    # ---- 4. finding + M7: one signal per exceedance, stable on re-evaluation
    findings = client.get("/api/v1/findings", headers=h, params={"asset_id": asset_id}).json()
    assert findings and all(f["asset_id"] == asset_id for f in findings)
    for _ in range(2):
        sigs = client.get(f"/api/v1/intelligence/assets/{asset_id}/signals", headers=h).json()
        hums = [s for s in sigs if s["signal_type"] == "HUMS_VIBRATION_EXCEEDANCE"]
        assert len(hums) == len(exceed)
    assert len({s["signal_key"] for s in sigs}) == len(sigs)

    # ---- 5. utilization: flight hours and cycles accumulate
    for minutes in (60, 30):
        assert client.post(f"{base}/{asset_id}/flights", headers=h, json={
            "flown_at": "2026-09-02T08:00:00Z", "duration_minutes": minutes, "cycles": 1}).status_code == 201
    util = client.get(f"{base}/{asset_id}/utilization", headers=h).json()
    assert (util["total_flights"], util["total_minutes"], util["total_cycles"]) == (2, 90, 2)

    # ---- 6. MRO: corrective work order against the ASSET (no Aircraft row exists for these airframes)
    wo = client.post("/api/v1/work-orders", headers=h, json={
        "asset_id": asset_id, "work_order_number": f"WO-{registration}", "title": "Investigate vibration excursion",
        "work_order_type": "CORRECTIVE"})
    assert wo.status_code == 201, wo.text
    assert wo.json()["asset_id"] == asset_id

    # ---- 7. audit trail records the journey (creation, sensors, batch ingest)
    actions = {a for (a,) in db_session.execute(select(AuditEvent.action).where(AuditEvent.organization_id == org.id))}
    assert {f"{family}.created", "hums_sensor.created", "data_source.ingested", "hums_exceedance.detected"} <= actions

    # ---- 8. LISA sees this family's assets only through its entitlement
    user = _user(client, h)
    fleet = execute_tool(db_session, user, "list_fleet_assets", {})["assets"]
    assert [x["registration"] for x in fleet] == [registration] and fleet[0]["asset_type"] == family.upper()
    health = execute_tool(db_session, user, "get_asset_hums_health", {"asset_id": asset_id})
    assert health is not None

    # ---- 9. isolation: other suites / tenants learn nothing
    other = "drones" if family == "helicopter" else "helicopters"
    assert client.get(f"/api/v1/{other}", headers=h).status_code == 403                    # other domains stay closed
    assert client.get("/api/v1/aircraft", headers=h).status_code == 403
    _org2, _s2, h2, _ = _customer(client, db_session, [_plan(db_session, suite, plan)])    # same suite, other tenant
    for p in (f"{base}/{asset_id}", f"{base}/{asset_id}/utilization", f"/api/v1/telemetry/assets/{asset_id}/latest"):
        assert client.get(p, headers=h2).status_code == 404, p
    r = client.get(f"/api/v1/hums/assets/{asset_id}/exceedances", headers=h2)      # tenant-scoped list: empty, never ours
    assert r.status_code == 404 or (r.status_code == 200 and r.json() == [])
    assert client.get("/api/v1/findings", headers=h2, params={"asset_id": asset_id}).json() == []
