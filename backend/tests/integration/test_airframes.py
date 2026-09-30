"""Helicopter and eVTOL/AAM suites: fleet APIs, suite boundaries, tenant/type isolation, components, flight hours and
cycles, maintenance, HUMS starter sensors, eVTOL batteries, and the generic /assets side door."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select

from app.models.audit_event import AuditEvent
from app.models.hums import HUMSSensor
from app.models.subscription import Subscription
from tests.integration.conftest import grant_features
from tests.integration.test_acquisition_pipeline import _drone, _org

HELI_FEATURES = ("helicopter_fleet_management", "hums", "flight_telemetry", "work_order_management")
EVTOL_FEATURES = ("evtol_fleet_management", "battery_analytics", "hums", "flight_telemetry")


def suite_org(client, db, tag, suite, features):
    """Organization whose ONLY subscription is `suite` (replaces the default drone plan from registration)."""
    org_id, h = _org(client, db, tag)
    db.execute(delete(Subscription).where(Subscription.organization_id == org_id))
    db.flush()
    grant_features(db, org_id, *features, suite_code=suite)
    return org_id, h


@pytest.fixture
def heli(client, db_session):
    return suite_org(client, db_session, "heli", "HELICOPTER", HELI_FEATURES)


@pytest.fixture
def evtol(client, db_session):
    return suite_org(client, db_session, "evtol", "EVTOL_AAM", EVTOL_FEATURES)


def make_heli(client, h, reg="HELI-1", **detail):
    r = client.post("/api/v1/helicopters", headers=h, json={
        "registration": reg, "manufacturer": "Airbus", "model": "H145",
        "detail": {"rotor_system": "SINGLE_MAIN_TAIL", "main_rotor_blade_count": 4, "engine_count": 2,
                   "max_takeoff_weight_kg": 3700, **detail}})
    assert r.status_code == 201, r.text
    return r.json()


def make_evtol(client, h, reg="EV-1", **detail):
    r = client.post("/api/v1/evtols", headers=h, json={
        "registration": reg, "manufacturer": "Acme", "model": "A1",
        "detail": {"configuration": "LIFT_CRUISE", "propulsor_count": 4, "battery_nominal_energy_kwh": 120.0,
                   "hv_bus_nominal_voltage_v": 800.0, "passenger_capacity": 4, **detail}})
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ CRUD + validation
def test_helicopter_crud_validation_and_audit_with_previous_values(client, db_session, heli):
    org_id, h = heli
    a = make_heli(client, h)
    assert a["asset_type"] == "HELICOPTER" and a["detail"]["engine_count"] == 2 and a["registration"] == "HELI-1"
    assert client.get(f"/api/v1/helicopters/{a['id']}", headers=h).json()["detail"]["rotor_system"] == "SINGLE_MAIN_TAIL"
    assert [x["id"] for x in client.get("/api/v1/helicopters", headers=h).json()] == [a["id"]]

    for bad in ({"rotor_system": "WARP_DRIVE"}, {"engine_count": 9}, {"max_takeoff_weight_kg": -1}, {"wings": 2},
                {"main_rotor_blade_count": "many"}):
        r = client.post("/api/v1/helicopters", headers=h, json={"registration": f"X{uuid.uuid4().hex[:5]}", "detail": bad})
        assert r.status_code == 422, (bad, r.text)
    assert client.post("/api/v1/helicopters", headers=h, json={"registration": "heli-1"}).status_code == 409  # case-insensitive dup

    r = client.patch(f"/api/v1/helicopters/{a['id']}", headers=h, json={"status": "MAINTENANCE", "detail": {"engine_count": 1}})
    assert r.status_code == 200 and r.json()["status"] == "MAINTENANCE" and r.json()["detail"]["engine_count"] == 1
    assert client.patch(f"/api/v1/helicopters/{a['id']}", headers=h, json={"status": "FLYING_CARPET"}).status_code == 422
    ev = db_session.execute(select(AuditEvent).where(AuditEvent.organization_id == org_id,
                                                     AuditEvent.action == "helicopter.updated")).scalar_one()
    assert ev.event_metadata["status"] == {"from": "ACTIVE", "to": "MAINTENANCE"}
    assert ev.event_metadata["engine_count"] == {"from": 2, "to": 1}


def test_evtol_crud_and_validation(client, heli, evtol):
    _, h = evtol
    a = make_evtol(client, h)
    assert a["asset_type"] == "EVTOL" and a["detail"]["configuration"] == "LIFT_CRUISE"
    for bad in ({"configuration": "BALLOON"}, {"propulsor_count": 0}, {"hv_bus_nominal_voltage_v": 0},
                {"engine_count": 2}):
        r = client.post("/api/v1/evtols", headers=h, json={"registration": f"E{uuid.uuid4().hex[:5]}", "detail": bad})
        assert r.status_code == 422, (bad, r.text)


def test_facility_must_belong_to_the_callers_tenant(client, db_session, heli):
    from app.models.facility import Facility

    _, h = heli
    other_org, _ = _org(client, db_session, "fac")
    fac = Facility(organization_id=other_org, name="Foreign hangar", code=f"F{uuid.uuid4().hex[:5]}", facility_type="HANGAR")
    db_session.add(fac)
    db_session.flush()
    r = client.post("/api/v1/helicopters", headers=h, json={"registration": "HF-1", "facility_id": str(fac.id)})
    assert r.status_code == 404


# ------------------------------------------------------------------ suite boundaries and isolation
def test_each_family_requires_its_own_suite_feature(client, db_session, heli, evtol):
    _, hh = heli
    _, he = evtol
    drone_org, hd = _org(client, db_session, "drone")
    body = {"registration": "ZZ-1"}
    for path in ("/api/v1/helicopters", "/api/v1/evtols"):
        r = client.post(path, headers=hd, json=body)                       # drone-suite org
        assert r.status_code == 403 and r.json()["error"]["code"] == "SUITE_ENTITLEMENT_REQUIRED", (path, r.text)
        assert client.get(path, headers=hd).status_code == 403
    assert client.post("/api/v1/evtols", headers=hh, json=body).status_code == 403          # helicopter org
    assert client.post("/api/v1/helicopters", headers=he, json=body).status_code == 403     # evtol org
    assert client.get("/api/v1/drones", headers=hh).status_code == 403                      # and not the drone domain


def test_generic_assets_endpoint_is_not_a_side_door_around_the_suite(client, db_session, heli):
    _, hh = heli
    drone_org, hd = _org(client, db_session, "side")
    for t in ("HELICOPTER", "EVTOL", "AAM"):
        r = client.post("/api/v1/assets", headers=hd, json={"asset_type": t, "registration": f"S-{t[:3]}"})
        assert r.status_code == 403, (t, r.text)
    assert client.post("/api/v1/assets", headers=hd, json={"asset_type": "OTHER", "registration": "S-OTH"}).status_code == 201
    assert client.post("/api/v1/assets", headers=hh, json={"asset_type": "HELICOPTER", "registration": "S-H"}).status_code == 201
    assert client.post("/api/v1/assets", headers=hh, json={"asset_type": "DRONE", "registration": "S-D"}).status_code == 403


def test_tenant_and_type_isolation(client, db_session, heli):
    _, ha = heli
    _, hb = suite_org(client, db_session, "heli2", "HELICOPTER", HELI_FEATURES)
    a = make_heli(client, ha)
    for method, path in (("get", f"/{a['id']}"), ("get", f"/{a['id']}/components"), ("get", f"/{a['id']}/flights"),
                         ("get", f"/{a['id']}/utilization"), ("get", f"/{a['id']}/maintenance-due"),
                         ("get", f"/{a['id']}/lifecycle-history"), ("post", f"/{a['id']}/hums/apply-template")):
        assert getattr(client, method)(f"/api/v1/helicopters{path}", headers=hb).status_code == 404, path
    assert client.patch(f"/api/v1/helicopters/{a['id']}", headers=hb, json={"status": "GROUNDED"}).status_code == 404
    assert client.get("/api/v1/helicopters", headers=hb).json() == []

    # a multi-suite org must not reach an asset of the other family through the wrong route
    grant_features(db_session, uuid.UUID(client.get("/api/v1/auth/me", headers=ha).json()["organization_id"]),
                   "drone_fleet_management", suite_code="DRONE_UAV")
    drone_id = _drone(client, ha, reg="MIX-D")
    assert client.get(f"/api/v1/helicopters/{drone_id}", headers=ha).status_code == 404
    assert client.get(f"/api/v1/helicopters/{drone_id}/flights", headers=ha).status_code == 404
    assert client.post(f"/api/v1/helicopters/{drone_id}/components", headers=ha,
                       json={"component_type": "ROTOR", "name": "x"}).status_code == 404
    assert client.get(f"/api/v1/drones/{a['id']}", headers=ha).status_code == 404


# ------------------------------------------------------------------ operations: components, hours/cycles, maintenance
def test_components_flight_hours_cycles_and_maintenance_views(client, heli):
    _, h = heli
    a = make_heli(client, h)
    c = client.post(f"/api/v1/helicopters/{a['id']}/components", headers=h,
                    json={"component_type": "ROTOR", "name": "Main rotor head", "serial_number": "MRH-001"})
    assert c.status_code == 201, c.text
    assert [x["component_type"] for x in client.get(f"/api/v1/helicopters/{a['id']}/components", headers=h).json()] == ["ROTOR"]

    for minutes, cycles in ((90, 2), (30, 1)):
        r = client.post(f"/api/v1/helicopters/{a['id']}/flights", headers=h, json={
            "flown_at": "2026-09-01T10:00:00Z", "duration_minutes": minutes, "cycles": cycles})
        assert r.status_code == 201, r.text
    u = client.get(f"/api/v1/helicopters/{a['id']}/utilization", headers=h).json()
    assert (u["total_flights"], u["total_minutes"], u["total_cycles"]) == (2, 120, 3), u
    assert client.get(f"/api/v1/helicopters/{a['id']}/flights", headers=h).json()["total"] == 2
    assert client.get(f"/api/v1/helicopters/{a['id']}/maintenance-due", headers=h).json() == []
    assert client.get(f"/api/v1/helicopters/{a['id']}/lifecycle-history", headers=h).status_code == 200
    assert client.post(f"/api/v1/helicopters/{a['id']}/flights", headers=h, json={
        "flown_at": "2026-09-01T10:00:00Z", "duration_minutes": 0}).status_code == 422


def test_evtol_batteries_need_battery_feature_and_stay_in_family(client, db_session, evtol):
    _, h = evtol
    a = make_evtol(client, h)
    r = client.post(f"/api/v1/evtols/{a['id']}/batteries", headers=h, json={
        "serial_number": "HVB-1", "manufacturer": "Acme", "model": "P120", "capacity_mah": 1000, "voltage": 800.0})
    assert r.status_code == 201, r.text
    assert len(client.get(f"/api/v1/evtols/{a['id']}/batteries", headers=h).json()) == 1
    # an eVTOL org WITHOUT battery_analytics is refused on the battery routes only
    _, h2 = suite_org(client, db_session, "evtol2", "EVTOL_AAM", ("evtol_fleet_management",))
    b = make_evtol(client, h2, reg="EV-2")
    assert client.get(f"/api/v1/evtols/{b['id']}", headers=h2).status_code == 200
    assert client.get(f"/api/v1/evtols/{b['id']}/batteries", headers=h2).status_code == 403


# ------------------------------------------------------------------ HUMS
def test_helicopter_hums_template_is_idempotent_and_binds_only_unambiguous_components(client, db_session, heli):
    org_id, h = heli
    a = make_heli(client, h)
    client.post(f"/api/v1/helicopters/{a['id']}/components", headers=h, json={"component_type": "ROTOR", "name": "Main"})
    client.post(f"/api/v1/helicopters/{a['id']}/components", headers=h, json={"component_type": "ROTOR", "name": "Tail"})
    client.post(f"/api/v1/helicopters/{a['id']}/components", headers=h, json={"component_type": "TRANSMISSION", "name": "MGB"})
    first = client.post(f"/api/v1/helicopters/{a['id']}/hums/apply-template", headers=h).json()
    assert sorted(first["created"]) == sorted(["MGB-TEMP", "MGB-VIB", "MR-VIB", "NR-RPM", "TR-VIB", "ENG1-TRQ"])
    assert first["skipped"] == []
    second = client.post(f"/api/v1/helicopters/{a['id']}/hums/apply-template", headers=h).json()
    assert second["created"] == [] and len(second["skipped"]) == 6
    sensors = {s.sensor_code: s for s in db_session.execute(
        select(HUMSSensor).where(HUMSSensor.organization_id == org_id)).scalars()}
    assert sensors["MGB-VIB"].component_id is not None          # exactly one transmission => bound
    assert sensors["MR-VIB"].component_id is None               # two rotors => ambiguous => NOT guessed
    assert sensors["MR-VIB"].measurement_type == "vibration"


def test_evtol_template_scales_with_propulsor_count(client, db_session, evtol):
    org_id, h = evtol
    a = make_evtol(client, h, propulsor_count=6)
    out = client.post(f"/api/v1/evtols/{a['id']}/hums/apply-template", headers=h).json()
    assert [c for c in out["created"] if c.startswith("PROP")] == [f"PROP{i}-VIB" for i in range(1, 7)]
    assert {"HVBUS-V", "HVBUS-I", "INV-TEMP", "MTR-TEMP", "BATT-TEMP"} <= set(out["created"])
    types = {s.sensor_code: s.measurement_type for s in db_session.execute(
        select(HUMSSensor).where(HUMSSensor.organization_id == org_id)).scalars()}
    assert types["HVBUS-V"] == "voltage" and types["HVBUS-I"] == "current" and types["PROP1-VIB"] == "vibration"


def test_hums_sensor_creation_cannot_target_another_tenants_asset(client, db_session, heli):
    _, h = heli
    other_org, other_h = _org(client, db_session, "victim")
    victim_asset = _drone(client, other_h, reg="VICTIM-1")
    mine = make_heli(client, h)
    payload = {"sensor_code": "X", "sensor_type": "ACCELEROMETER", "measurement_type": "vibration", "unit": "mm/s"}
    r = client.post("/api/v1/hums/sensors", headers=h, json={**payload, "asset_id": victim_asset})
    assert r.status_code == 404
    assert client.post("/api/v1/hums/sensors", headers=h, json={**payload, "asset_id": mine["id"]}).status_code == 200
    comp = client.post(f"/api/v1/helicopters/{mine['id']}/components", headers=h,
                       json={"component_type": "ROTOR", "name": "R"}).json()["id"]
    foreign_comp = client.post(f"/api/v1/drones/{victim_asset}/components", headers=other_h,
                               json={"component_type": "MOTOR", "name": "M"}).json()["id"]
    bad = client.post("/api/v1/hums/sensors", headers=h, json={**payload, "sensor_code": "Y", "asset_id": mine["id"],
                                                               "component_id": foreign_comp})
    assert bad.status_code == 404 and comp
