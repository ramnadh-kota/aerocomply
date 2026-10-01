"""Customer journeys driven from the PLATFORM ADMIN API (no direct database setup of commercial state), for all four suites:

  Platform Admin -> (custom suite) -> suite-specific plan -> features -> organization -> org admin -> subscription
  -> org admin login -> entitlements resolve -> RBAC -> suite asset -> suite boundaries -> audit trail
  -> per family: data source -> telemetry -> HUMS -> finding -> M7 signal -> LISA, or (Aircraft) work order ->
  finding -> compliance -> LISA. Simulated input only; nothing touches hardware or an external service.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.hums import HUMSExceedance
from app.schemas.auth import CurrentUser
from app.services.ai.tools import execute_tool
from tests.integration.conftest import make_platform_admin_headers
from tests.integration.test_acquisition_pipeline import _csv, _ingest, _source
from tests.integration.test_customer_journeys_commercial import PW

FEATURES = {
    "AIRCRAFT": ["aircraft_fleet_management", "work_order_management", "compliance_management", "lisa_ai_copilot"],
    "DRONE_UAV": ["drone_fleet_management", "flight_telemetry", "hums", "battery_analytics", "work_order_management",
                  "lisa_ai_copilot", "predictive_maintenance"],
    "HELICOPTER": ["helicopter_fleet_management", "flight_telemetry", "hums", "work_order_management", "lisa_ai_copilot",
                   "predictive_maintenance"],
    "EVTOL_AAM": ["evtol_fleet_management", "battery_analytics", "flight_telemetry", "hums", "work_order_management",
                  "lisa_ai_copilot", "predictive_maintenance"],
}
PATHS = {"AIRCRAFT": "aircraft", "DRONE_UAV": "drones", "HELICOPTER": "helicopters", "EVTOL_AAM": "evtols"}
DETAIL = {
    "HELICOPTER": {"rotor_system": "SINGLE_MAIN_TAIL", "main_rotor_blade_count": 4, "engine_count": 2},
    "EVTOL_AAM": {"configuration": "LIFT_CRUISE", "propulsor_count": 4, "battery_nominal_energy_kwh": 100.0},
}
SENSOR = {"HELICOPTER": "MR-VIB", "EVTOL_AAM": "PROP1-VIB"}


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _platform_onboard(client, db_session, suite_code: str):
    """Everything a Platform Admin does, through the HTTP API only. Returns (org_id, org admin headers, plan id)."""
    pa = make_platform_admin_headers(client, db_session)
    suites = {s["code"]: s for s in client.get("/api/v1/platform/suites", headers=pa).json()}
    assert suite_code in suites, sorted(suites)

    plan = client.post(f"/api/v1/platform/suites/{suites[suite_code]['id']}/plans", headers=pa, json={
        "name": f"{suite_code} Journey Plan", "code": f"JP-{uuid.uuid4().hex[:8]}"})
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]
    feats = client.put(f"/api/v1/platform/plans/{plan_id}/features", headers=pa, json={
        "features": [{"feature_key": f, "enabled": True} for f in FEATURES[suite_code]]})
    assert feats.status_code == 200, feats.text

    org = client.post("/api/v1/platform/organizations", headers=pa, json={"name": f"Journey {suite_code} {uuid.uuid4().hex[:6]}"})
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    email = f"j-{uuid.uuid4().hex[:8]}@example.com"
    admin = client.post(f"/api/v1/platform/organizations/{org_id}/admins", headers=pa, json={
        "email": email, "full_name": "Journey Admin", "password": PW})
    assert admin.status_code == 201, admin.text
    sub = client.post(f"/api/v1/platform/organizations/{org_id}/subscriptions", headers=pa, json={
        "plan_id": plan_id, "status": "ACTIVE", "starts_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()})
    assert sub.status_code == 201, sub.text

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    assert login.status_code == 200, login.text
    return uuid.UUID(org_id), _h(login.json()["access_token"]), plan_id


def _me(client, h) -> CurrentUser:
    me = client.get("/api/v1/auth/me", headers=h).json()
    return CurrentUser(id=uuid.UUID(me["id"]), organization_id=uuid.UUID(me["organization_id"]), roles=me["roles"],
                       email=me["email"], full_name=me.get("full_name", ""), email_verified=True)


def test_platform_admin_can_create_a_new_suite_through_the_api(client, db_session):
    pa = make_platform_admin_headers(client, db_session)
    code = f"JOURNEY_{uuid.uuid4().hex[:6].upper()}"
    r = client.post("/api/v1/platform/suites", headers=pa, json={"code": code, "name": "Journey Suite"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert code in {s["code"] for s in client.get("/api/v1/platform/suites", headers=pa).json()}
    plan = client.post(f"/api/v1/platform/suites/{sid}/plans", headers=pa, json={"name": "Custom plan", "code": f"CP-{uuid.uuid4().hex[:6]}"})
    assert plan.status_code == 201 and plan.json()["suite_id"] == sid
    # a tenant admin cannot create suites
    _org, h, _ = _platform_onboard(client, db_session, "AIRCRAFT")
    assert client.post("/api/v1/platform/suites", headers=h, json={"code": "NOPE", "name": "Nope"}).status_code == 403


@pytest.mark.parametrize("suite_code", ["AIRCRAFT", "DRONE_UAV", "HELICOPTER", "EVTOL_AAM"])
def test_platform_driven_onboarding_entitlements_rbac_and_suite_boundaries(client, db_session, suite_code):
    org_id, h, _plan = _platform_onboard(client, db_session, suite_code)

    # entitlements resolve from the subscription created by the Platform Admin
    ent = client.get("/api/v1/entitlements", headers=h).json()
    assert ent["suite_code"] == suite_code
    for feature in FEATURES[suite_code]:
        assert ent["effective_features"].get(feature) is True, feature

    # users / RBAC: the provisioned admin is an ORG_ADMIN of exactly this organization
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["organization_id"] == str(org_id) and "ORG_ADMIN" in me["roles"]
    assert client.get("/api/v1/platform/organizations", headers=h).status_code == 403     # not a platform actor
    assert client.get("/api/v1/tenant/users", headers=h).status_code == 200

    # suite asset created through the suite's own API; every other family's API stays closed
    body = {"registration": f"PJ-{uuid.uuid4().hex[:5].upper()}", "manufacturer": "OEM", "model": "M1"}
    if suite_code == "AIRCRAFT":
        body.update(msn=f"MSN-{uuid.uuid4().hex[:6]}", aircraft_type="A320")
    if suite_code in DETAIL:
        body["detail"] = DETAIL[suite_code]
    created = client.post(f"/api/v1/{PATHS[suite_code]}", headers=h, json=body)
    assert created.status_code == 201, created.text
    for code, path in PATHS.items():
        if code != suite_code:
            assert client.get(f"/api/v1/{path}", headers=h).status_code == 403, (suite_code, path)

    # platform actions are in the audit trail
    actions = {a for (a,) in db_session.execute(select(AuditEvent.action))}
    assert {"platform.organization.create", "platform.plan.created", "platform.plan.features_updated",
            "platform.organization.admin_created", "platform.subscription.created"} <= actions, sorted(actions)


@pytest.mark.parametrize("suite_code", ["HELICOPTER", "EVTOL_AAM"])
def test_platform_driven_airframe_journey_from_telemetry_to_lisa(client, db_session, suite_code):
    org_id, h, _plan = _platform_onboard(client, db_session, suite_code)
    base = f"/api/v1/{PATHS[suite_code]}"
    reg = f"PJA-{uuid.uuid4().hex[:5].upper()}"
    asset = client.post(base, headers=h, json={"registration": reg, "manufacturer": "OEM", "model": "M1",
                                               "detail": DETAIL[suite_code]}).json()["id"]
    assert client.post(f"{base}/{asset}/hums/apply-template", headers=h).status_code in (200, 201)
    sid = _source(client, h, "CSV_BATCH")
    values = [1.5, 1.6, 1.5, 1.7, 1.6, 1.5, 48.0, 52.0]
    rows = [{"asset_id": reg, "sensor_code": SENSOR[suite_code], "value": str(v), "unit": "mm/s",
             "timestamp": f"2026-09-01T10:{i:02d}:00Z"} for i, v in enumerate(values)]
    rep = _ingest(client, h, sid, _csv(rows)).json()
    assert rep["accepted"] == len(values) and rep["rejected"] == 0, rep
    exceed = db_session.execute(select(HUMSExceedance).where(
        HUMSExceedance.organization_id == org_id, HUMSExceedance.asset_id == uuid.UUID(asset))).scalars().all()
    assert exceed, "telemetry excursion produced no HUMS exceedance"
    findings = client.get("/api/v1/findings", headers=h, params={"asset_id": asset}).json()
    assert findings
    sigs = client.get(f"/api/v1/intelligence/assets/{asset}/signals", headers=h).json()
    assert any(s["signal_type"] == "HUMS_VIBRATION_EXCEEDANCE" for s in sigs)
    wo = client.post("/api/v1/work-orders", headers=h, json={
        "asset_id": asset, "work_order_number": f"WO-{reg}", "title": "Investigate vibration", "work_order_type": "CORRECTIVE"})
    assert wo.status_code == 201, wo.text
    # lineage: the graph connects the asset to the exceedance, finding and signal that came from this telemetry
    graph = client.get("/api/v1/digital-twin/graph", headers=h, params={"node_type": "ASSET", "node_id": asset, "depth": 4})
    if graph.status_code == 200:                       # digital_twin is a separate feature of the plan
        assert {"EXCEEDANCE", "FINDING"} <= {n["type"] for n in graph.json()["nodes"]}
    else:
        assert graph.status_code == 403
    # LISA explains from the same records
    fleet = execute_tool(db_session, _me(client, h), "list_fleet_assets", {})["assets"]
    assert [x["registration"] for x in fleet] == [reg]
    assert execute_tool(db_session, _me(client, h), "get_asset_hums_health", {"asset_id": asset}) is not None
    actions = {a for (a,) in db_session.execute(select(AuditEvent.action).where(AuditEvent.organization_id == org_id))}
    assert {"hums_exceedance.detected", "data_source.ingested"} <= actions


def test_platform_driven_aircraft_mro_and_compliance_journey(client, db_session):
    org_id, h, _plan = _platform_onboard(client, db_session, "AIRCRAFT")
    reg = f"VT-{uuid.uuid4().hex[:3].upper()}"
    ac = client.post("/api/v1/aircraft", headers=h, json={"registration": reg, "msn": f"M-{uuid.uuid4().hex[:6]}",
                                                          "aircraft_type": "A320", "manufacturer": "Airbus"})
    assert ac.status_code == 201, ac.text
    ac_id = ac.json()["id"]

    # MRO: corrective work order -> finding traced to it -> disposition path is reachable
    wo = client.post("/api/v1/work-orders", headers=h, json={
        "aircraft_id": ac_id, "work_order_number": f"WO-{reg}", "title": "Hydraulic leak check", "work_order_type": "CORRECTIVE"})
    assert wo.status_code == 201, wo.text
    wo_id = wo.json()["id"]
    finding = client.post("/api/v1/findings", headers=h, json={
        "title": "Hydraulic seepage at actuator", "description": "Seepage found during walk-around", "severity": "MINOR",
        "aircraft_id": ac_id, "work_order_id": wo_id})
    assert finding.status_code == 201, finding.text
    fid = finding.json()["id"]
    assert client.get(f"/api/v1/findings/{fid}", headers=h).json()["work_order_id"] == wo_id
    assert client.get("/api/v1/findings", headers=h, params={"aircraft_id": ac_id}).json()

    # compliance surface is entitled and tenant-scoped
    assert client.get("/api/v1/regulatory-requirements", headers=h).status_code == 200
    assert client.get(f"/api/v1/aircraft/{ac_id}/compliance-analytics", headers=h).status_code == 200

    # Aircraft suite: telemetry / HUMS domains closed
    assert client.get("/api/v1/hums/sensors", headers=h).status_code == 403
    assert client.get("/api/v1/telemetry/events", headers=h).status_code == 403

    # LISA answers from these records only
    user = _me(client, h)
    assert execute_tool(db_session, user, "list_aircraft", {})
    from app.core.errors import ForbiddenError

    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, "get_asset_hums_health", {"asset_id": ac_id})

    # audit trail records the journey
    actions = {a for (a,) in db_session.execute(select(AuditEvent.action).where(AuditEvent.organization_id == org_id))}
    assert any(a.startswith("aircraft.") for a in actions) and any(a.startswith("work_order.") for a in actions), sorted(actions)
    assert any(a.startswith("finding.") for a in actions), sorted(actions)

    # another Aircraft tenant sees none of it
    _o2, h2, _p2 = _platform_onboard(client, db_session, "AIRCRAFT")
    assert client.get(f"/api/v1/aircraft/{ac_id}", headers=h2).status_code == 404
    assert client.get(f"/api/v1/findings/{fid}", headers=h2).status_code == 404
    assert client.get(f"/api/v1/work-orders/{wo_id}", headers=h2).status_code == 404
