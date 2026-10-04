from __future__ import annotations

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.organization import Organization
from app.models.user import User
from app.services.entitlement_service import resolve_entitlements
from scripts.seed_m22_demo_tenants import (
    DRONE_DEMO_ORG_NAME,
    AIRCRAFT_DEMO_ORG_NAME,
    DEMO_PASSWORD,
    seed_both_m22_demo_tenants,
)


def _auth_headers(client, email: str, password: str = DEMO_PASSWORD) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_m22_demo_tenants_seeding_and_product_isolation(client, db_session: Session):
    """Verifies that M22 creates two independent demo tenants and enforces strict mutual exclusion."""
    res = seed_both_m22_demo_tenants(db_session, reset=True)
    assert res["status"] == "SUCCESS"

    # 1. Inspect Drone Demo Tenant
    drone_org = db_session.execute(select(Organization).where(Organization.name == DRONE_DEMO_ORG_NAME)).scalar_one()
    drone_assets = db_session.execute(select(Asset).where(Asset.organization_id == drone_org.id)).scalars().all()
    drone_aircraft = db_session.execute(select(Aircraft).where(Aircraft.organization_id == drone_org.id)).scalars().all()

    assert len(drone_assets) == 5
    assert len(drone_aircraft) == 0  # Zero aircraft in drone demo tenant
    assert all(a.asset_type == AssetType.DRONE for a in drone_assets)

    drone_ent = resolve_entitlements(db_session, organization_id=drone_org.id)
    assert drone_ent.suite_code == "DRONE_UAV"
    assert drone_ent.effective_features.get("drone_fleet_management") is True
    assert drone_ent.effective_features.get("aircraft_fleet_management") is not True

    # 2. Inspect Aircraft Demo Tenant
    aircraft_org = db_session.execute(select(Organization).where(Organization.name == AIRCRAFT_DEMO_ORG_NAME)).scalar_one()
    aircraft_assets = db_session.execute(select(Asset).where(Asset.organization_id == aircraft_org.id)).scalars().all()
    aircraft_planes = db_session.execute(select(Aircraft).where(Aircraft.organization_id == aircraft_org.id)).scalars().all()

    assert len(aircraft_planes) == 2
    assert len(aircraft_assets) == 0  # Zero generic/drone assets in aircraft demo tenant

    aircraft_ent = resolve_entitlements(db_session, organization_id=aircraft_org.id)
    assert aircraft_ent.suite_code == "AIRCRAFT"
    assert aircraft_ent.effective_features.get("aircraft_fleet_management") is True
    assert aircraft_ent.effective_features.get("drone_fleet_management") is not True

    # 3. HTTP API Verification & Suite Boundary Tests
    drone_headers = _auth_headers(client, "drone.admin@kotaaerospace.com")
    aircraft_headers = _auth_headers(client, "aircraft.admin@kotaaerospace.com")

    # Drone admin: can access /api/v1/drones, CANNOT access /api/v1/aircraft
    r_drone_ok = client.get("/api/v1/drones", headers=drone_headers)
    assert r_drone_ok.status_code == 200
    assert len(r_drone_ok.json()) == 5

    r_drone_forbidden = client.get("/api/v1/aircraft", headers=drone_headers)
    assert r_drone_forbidden.status_code == 403  # Enforces suite restriction

    # Aircraft admin: can access /api/v1/aircraft, CANNOT access /api/v1/drones
    r_ac_ok = client.get("/api/v1/aircraft", headers=aircraft_headers)
    assert r_ac_ok.status_code == 200
    assert len(r_ac_ok.json()) == 2

    r_ac_forbidden = client.get("/api/v1/drones", headers=aircraft_headers)
    assert r_ac_forbidden.status_code == 403  # Enforces suite restriction

    # Direct mission access: Drone admin can list missions, Aircraft admin gets 403
    assert client.get("/api/v1/missions", headers=drone_headers).status_code == 200
    assert client.get("/api/v1/missions", headers=aircraft_headers).status_code == 403
