"""H6 Integration Tests: digital twin identity/snapshot aggregation,
component hierarchy, genealogy (component movement between assets), unified
timeline, H3/H4/H5 integration, consistency detection, safety boundaries
(twin never mutates authoritative state), tenant isolation, and RBAC.
"""

import datetime
import uuid

import pytest
from tests.integration.conftest import grant_features
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support.tokens import mint_token as create_access_token
from app.models.asset import Asset, AssetType
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.installation_history import ComponentInstallation
from app.models.organization import Organization
from app.models.user import User


def _auth_headers(user: User, roles: list[str] | None = None) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id, organization_id=user.organization_id, roles=roles or ["ORG_ADMIN"],
        email=user.email, full_name=user.full_name, email_verified=True,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def org_a(db_session: Session) -> Organization:
    org = Organization(name=f"H6 Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    grant_features(db_session, org.id, 'digital_twin', 'hums', 'mro_intelligence')
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"H6 Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    grant_features(db_session, org.id, 'digital_twin', 'hums', 'mro_intelligence')
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id, email=f"engineer.{uuid.uuid4().hex[:6]}@a.com", full_name="H6 Engineer A",
        hashed_password="pw", is_active=True, email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_b(db_session: Session, org_b: Organization) -> User:
    user = User(
        organization_id=org_b.id, email=f"engineer.{uuid.uuid4().hex[:6]}@b.com", full_name="H6 Engineer B",
        hashed_password="pw", is_active=True, email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def asset_a(db_session: Session, org_a: Organization) -> Asset:
    asset = Asset(
        organization_id=org_a.id, asset_type=AssetType.AIRCRAFT,
        registration=f"H6-{uuid.uuid4().hex[:5].upper()}", serial_number=f"SN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def asset_a2(db_session: Session, org_a: Organization) -> Asset:
    asset = Asset(
        organization_id=org_a.id, asset_type=AssetType.AIRCRAFT,
        registration=f"H6-{uuid.uuid4().hex[:5].upper()}", serial_number=f"SN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def component_a(db_session: Session, org_a: Organization, asset_a: Asset) -> Component:
    component = Component(
        organization_id=org_a.id, asset_id=asset_a.id, component_type=ComponentType.ENGINE,
        name="Engine 1", serial_number=f"CMP-{uuid.uuid4().hex[:6]}", status=ComponentStatus.INSTALLED,
    )
    db_session.add(component)
    db_session.commit()
    db_session.refresh(component)
    install = ComponentInstallation(
        organization_id=org_a.id, component_id=component.id, asset_id=asset_a.id,
        installed_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10),
    )
    db_session.add(install)
    db_session.commit()
    return component


def _auth(user_a):
    return _auth_headers(user_a)


def test_asset_snapshot_identity_and_sections(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth(user_a)
    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["identity"]["asset_id"] == str(asset_a.id)
    assert body["identity"]["asset_type"] == "AIRCRAFT"
    assert body["maintenance"]["availability"] == "AVAILABLE"
    assert body["compliance"]["availability"] == "AVAILABLE"
    assert body["readiness"]["availability"] == "AVAILABLE"
    assert body["diagnostics"] == []
    assert body["prognostics"] == []
    assert "generated_at" in body


def test_component_hierarchy_reflects_real_components(client: TestClient, user_a: User, asset_a: Asset, component_a: Component):
    headers = _auth(user_a)
    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/components", headers=headers)
    assert resp.status_code == 200
    nodes = resp.json()
    assert len(nodes) == 1
    assert nodes[0]["component"]["id"] == str(component_a.id)
    assert nodes[0]["diagnostic_count"] == 0


def test_component_genealogy_tracks_movement_between_assets(
    client: TestClient, db_session: Session, user_a: User, asset_a: Asset, asset_a2: Asset, component_a: Component
):
    """H6-B: component moves from asset_a to asset_a2 -- genealogy must show both spans."""
    headers = _auth(user_a)

    # Remove from asset_a, install on asset_a2.
    open_install = db_session.query(ComponentInstallation).filter(
        ComponentInstallation.component_id == component_a.id, ComponentInstallation.removed_at.is_(None)
    ).one()
    open_install.removed_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2)
    db_session.add(
        ComponentInstallation(
            organization_id=asset_a.organization_id, component_id=component_a.id, asset_id=asset_a2.id,
            installed_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1),
        )
    )
    component_a.asset_id = asset_a2.id
    db_session.commit()

    resp = client.get(f"/api/v1/digital-twin/components/{component_a.id}/genealogy", headers=headers)
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 2
    assert entries[0]["asset_id"] == str(asset_a.id)
    assert entries[0]["is_current"] is False
    assert entries[0]["removed_at"] is not None
    assert entries[1]["asset_id"] == str(asset_a2.id)
    assert entries[1]["is_current"] is True


def test_component_snapshot_includes_current_installation(client: TestClient, user_a: User, asset_a: Asset, component_a: Component):
    headers = _auth(user_a)
    resp = client.get(f"/api/v1/digital-twin/components/{component_a.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_asset_id"] == str(asset_a.id)
    assert body["genealogy_entry_count"] == 1


def _create_sensor(client: TestClient, headers: dict, asset_id: str, component_id: str | None = None) -> dict:
    payload = {
        "asset_id": asset_id, "sensor_code": f"SENS-{uuid.uuid4().hex[:6]}", "sensor_type": "ACCELEROMETER",
        "measurement_type": "vibration", "unit": "mm/s",
    }
    if component_id:
        payload["component_id"] = component_id
    resp = client.post("/api/v1/hums/sensors", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingest(client: TestClient, headers: dict, sensor_id: str, values: list[float], base_minutes: int) -> None:
    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {"recorded_at": (now - datetime.timedelta(minutes=base_minutes) + datetime.timedelta(seconds=i)).isoformat(), "value": v, "unit": "mm/s"}
        for i, v in enumerate(values)
    ]
    resp = client.post(f"/api/v1/hums/sensors/{sensor_id}/readings", headers=headers, json={"readings": readings})
    assert resp.status_code == 200, resp.text


def test_h3_h4_h5_integration_reflected_in_twin(client: TestClient, user_a: User, asset_a: Asset, component_a: Component):
    """H6-D/E/F: HUMS health/diagnostic/prognostic state surfaces in the twin without recomputation."""
    headers = _auth(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), component_id=str(component_a.id))

    for b in range(8):
        jitter = 1.0 + 0.07 * (((b % 3) - 1))
        _ingest(client, headers, sensor["id"], [1.0 * jitter] * 20, base_minutes=(9 - b) * 60)
    _ingest(client, headers, sensor["id"], [1.0] * 18 + [8.0, -6.0], base_minutes=0)

    snapshot = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers).json()
    assert snapshot["health"] is not None
    assert snapshot["health"]["state"] in ("DEGRADED", "WARNING", "CRITICAL", "WATCH")
    assert len(snapshot["diagnostics"]) >= 1
    assert len(snapshot["prognostics"]) >= 1

    # Independently query H3/H4/H5 directly and confirm the twin didn't recompute a different answer.
    direct_health = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers).json()
    assert snapshot["health"]["state"] == direct_health["state"]

    direct_diagnostics = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers).json()
    assert {d["id"] for d in snapshot["diagnostics"]} == {d["id"] for d in direct_diagnostics}


def test_timeline_includes_component_and_hums_events_chronologically(
    client: TestClient, user_a: User, asset_a: Asset, component_a: Component
):
    """H6-G."""
    headers = _auth(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), component_id=str(component_a.id))
    for b in range(8):
        _ingest(client, headers, sensor["id"], [1.0] * 20, base_minutes=(9 - b) * 60)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/timeline", headers=headers)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) > 0
    event_types = {e["event_type"] for e in events}
    assert "COMPONENT_INSTALLED" in event_types
    # Chronological (descending).
    timestamps = [e["occurred_at"] for e in events]
    assert timestamps == sorted(timestamps, reverse=True)
    for e in events:
        assert e["source_type"] and e["source_id"]  # every event traces to a real source record


def test_consistency_detects_installation_asset_mismatch(
    client: TestClient, db_session: Session, user_a: User, asset_a: Asset, asset_a2: Asset
):
    """H6-H: intentional derived-state mismatch must be detected, not silently ignored."""
    headers = _auth(user_a)
    component = Component(
        organization_id=asset_a.organization_id, asset_id=asset_a.id, component_type=ComponentType.ENGINE,
        name="Engine Mismatch", serial_number=f"CMP-{uuid.uuid4().hex[:6]}", status=ComponentStatus.INSTALLED,
    )
    db_session.add(component)
    db_session.commit()
    db_session.refresh(component)
    # Bug scenario: installation record points to a DIFFERENT asset than Component.asset_id.
    db_session.add(
        ComponentInstallation(
            organization_id=asset_a.organization_id, component_id=component.id, asset_id=asset_a2.id,
            installed_at=datetime.datetime.now(datetime.UTC),
        )
    )
    db_session.commit()

    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/consistency", headers=headers)
    assert resp.status_code == 200
    warnings = resp.json()
    assert any(w["check"] == "INSTALLATION_ASSET_MISMATCH" for w in warnings)


def test_consistency_clean_for_well_formed_data(client: TestClient, user_a: User, asset_a: Asset, component_a: Component):
    headers = _auth(user_a)
    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/consistency", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_twin_never_mutates_authoritative_asset_state(client: TestClient, db_session: Session, user_a: User, asset_a: Asset, component_a: Component):
    """Safety boundary: reading the twin must never change asset status, readiness, or HUMS state
    beyond what the underlying H3/H4/H5 evaluation itself already does as a documented side effect."""
    headers = _auth(user_a)
    original_status = asset_a.status

    client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers)
    client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers)

    db_session.expire_all()
    from app.models.asset import Asset as AssetModel

    refreshed = db_session.get(AssetModel, asset_a.id)
    assert refreshed.status == original_status  # unchanged


def test_cross_tenant_twin_isolation(client: TestClient, user_a: User, user_b: User, asset_a: Asset, component_a: Component):
    """H6-I."""
    headers_a = _auth(user_a)
    headers_b = _auth_headers(user_b)

    resp_b_snapshot = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers_b)
    assert resp_b_snapshot.status_code == 404

    resp_b_genealogy = client.get(f"/api/v1/digital-twin/components/{component_a.id}/genealogy", headers=headers_b)
    assert resp_b_genealogy.status_code == 200
    assert resp_b_genealogy.json() == []  # org B sees no installations for org A's component

    resp_b_timeline = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/timeline", headers=headers_b)
    assert resp_b_timeline.status_code == 200
    assert resp_b_timeline.json() == []  # same "safe empty" pattern as H3's list-style endpoints (deviations/trends)


def test_viewer_can_read_twin_snapshot(client: TestClient, user_a: User, asset_a: Asset):
    headers_viewer = _auth_headers(user_a, roles=["VIEWER"])
    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers_viewer)
    assert resp.status_code == 200


def test_unauthorized_role_cannot_read_twin(client: TestClient, db_session: Session, org_a: Organization, asset_a: Asset):
    """A role with no permission set at all should be denied."""
    user = User(
        organization_id=org_a.id, email=f"noperm.{uuid.uuid4().hex[:6]}@a.com", full_name="No Permission User",
        hashed_password="pw", is_active=True, email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(
        user_id=user.id, organization_id=user.organization_id, roles=["PLATFORM_STAFF"],
        email=user.email, full_name=user.full_name, email_verified=True,
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get(f"/api/v1/digital-twin/assets/{asset_a.id}/snapshot", headers=headers)
    assert resp.status_code == 403
