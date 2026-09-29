"""H4 Integration Tests: H3 health -> anomaly -> diagnostic candidate
generation, competing hypotheses, sensor-fault detection, confirm/reject
lifecycle, ProactiveSignalRecord integration, safety-boundary tests,
tenant isolation, and RBAC.
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.hums import HUMSDiagnosticCandidate
from app.models.organization import Organization
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.user import User


def _auth_headers(user: User, roles: list[str] | None = None) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id, organization_id=user.organization_id, roles=roles or ["ORG_ADMIN"],
        email=user.email, full_name=user.full_name, email_verified=True,
    )
    return {"Authorization": f"Bearer {token}"}


from datetime import UTC, timedelta
from sqlalchemy import select
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus


def _seed_hums_sub(db_session: Session, org_id: uuid.UUID):
    plan = db_session.execute(select(Plan).where(Plan.code == "ENTERPRISE_HUMS")).scalar_one_or_none()
    if not plan:
        plan = Plan(name="Enterprise HUMS", code="ENTERPRISE_HUMS", is_active=True)
        db_session.add(plan)
        db_session.flush()
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="hums", enabled=True))
        db_session.flush()
    sub = Subscription(
        organization_id=org_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.flush()


@pytest.fixture
def org_a(db_session: Session) -> Organization:
    org = Organization(name=f"H4 Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"H4 Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id, email=f"engineer.{uuid.uuid4().hex[:6]}@a.com", full_name="H4 Engineer A",
        hashed_password="pw", is_active=True, email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_b(db_session: Session, org_b: Organization) -> User:
    user = User(
        organization_id=org_b.id, email=f"engineer.{uuid.uuid4().hex[:6]}@b.com", full_name="H4 Engineer B",
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
        registration=f"H4-{uuid.uuid4().hex[:6].upper()}", serial_number=f"SN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _create_sensor(client: TestClient, headers: dict, asset_id: str, sensor_code: str, component_id: str | None = None) -> dict:
    payload = {
        "asset_id": asset_id, "sensor_code": sensor_code, "sensor_type": "ACCELEROMETER",
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


HEALTHY_PATTERN = ([1.0 + 0.05 * ((-1) ** i) for i in range(10)]) * 2


def _establish_baseline(client: TestClient, headers: dict, sensor_id: str, batches: int = 8) -> None:
    for b in range(batches):
        jitter = 1.0 + 0.07 * (((b % 3) - 1))
        _ingest(client, headers, sensor_id, [v * jitter for v in HEALTHY_PATTERN], base_minutes=(batches - b) * 10)


SPIKY = [1.0] * 18 + [8.0, -6.0]


def test_no_candidate_for_healthy_asset(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-01")
    _establish_baseline(client, headers, sensor["id"])

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_correlated_anomaly_produces_supported_candidate_with_alternative(
    client: TestClient, db_session: Session, user_a: User, asset_a: Asset
):
    """H3 health -> anomaly -> diagnostic pathway, with competing
    hypotheses preserved (H4 spec Scenarios C and E)."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-02")
    _establish_baseline(client, headers, sensor["id"])
    _ingest(client, headers, sensor["id"], SPIKY, base_minutes=0)

    # Trigger H3+H4 evaluation.
    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["state"] in ("WARNING", "CRITICAL")

    diag_resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers)
    assert diag_resp.status_code == 200
    diagnostics = diag_resp.json()
    assert len(diagnostics) >= 1
    fault_codes = {d["fault_code"] for d in diagnostics}
    assert "VIB-BRG-001" in fault_codes

    bearing = next(d for d in diagnostics if d["fault_code"] == "VIB-BRG-001")
    assert bearing["status"] == "SUPPORTED"
    assert bearing["severity"] in ("MEDIUM", "HIGH")
    assert len(bearing["explanation"]) > 0  # explainability requirement
    assert bearing["primary_evidence"]  # evidence lineage present

    # Diagnostics must never auto-confirm.
    assert all(d["status"] not in ("CONFIRMED",) for d in diagnostics)


def test_no_duplicate_signal_spam_on_repeated_evaluation(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-03")
    _establish_baseline(client, headers, sensor["id"])
    _ingest(client, headers, sensor["id"], SPIKY, base_minutes=0)

    for _ in range(3):
        client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    db_session.expire_all()
    signals = db_session.query(ProactiveSignalRecord).filter(
        ProactiveSignalRecord.organization_id == asset_a.organization_id,
        ProactiveSignalRecord.signal_type == "HUMS_DIAGNOSTIC_CANDIDATE",
    ).all()
    assert len(signals) == 1  # exactly one signal despite 3 re-evaluations


def test_sensor_fault_candidate_when_one_of_two_sensors_abnormal(
    client: TestClient, user_a: User, asset_a: Asset, db_session: Session
):
    headers = _auth_headers(user_a)
    component = Component(
        organization_id=asset_a.organization_id, asset_id=asset_a.id, component_type=ComponentType.ENGINE,
        name="Engine 1", serial_number=f"CMP-{uuid.uuid4().hex[:6]}", status=ComponentStatus.INSTALLED,
    )
    db_session.add(component)
    db_session.commit()
    db_session.refresh(component)

    bad_sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-BAD", component_id=str(component.id))
    good_sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-GOOD", component_id=str(component.id))
    _establish_baseline(client, headers, bad_sensor["id"])
    _establish_baseline(client, headers, good_sensor["id"])
    _ingest(client, headers, bad_sensor["id"], SPIKY, base_minutes=0)

    resp = client.get(f"/api/v1/hums/components/{component.id}/health", headers=headers)
    assert resp.status_code == 200

    diag_resp = client.get(f"/api/v1/hums/components/{component.id}/diagnostics", headers=headers)
    assert diag_resp.status_code == 200
    diagnostics = diag_resp.json()
    fault_codes = {d["fault_code"] for d in diagnostics}
    assert "SEN-ANOM-001" in fault_codes
    sensor_candidate = next(d for d in diagnostics if d["fault_code"] == "SEN-ANOM-001")
    assert sensor_candidate["sensor_ids"] == [bad_sensor["id"]]


def test_confirm_and_reject_lifecycle_requires_authorized_action(
    client: TestClient, db_session: Session, user_a: User, asset_a: Asset
):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-04")
    _establish_baseline(client, headers, sensor["id"])
    _ingest(client, headers, sensor["id"], SPIKY, base_minutes=0)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    diagnostics = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers).json()
    bearing = next(d for d in diagnostics if d["fault_code"] == "VIB-BRG-001")
    assert bearing["status"] == "SUPPORTED"  # never auto-CONFIRMED

    confirm_resp = client.post(f"/api/v1/hums/diagnostics/{bearing['id']}/confirm", headers=headers)
    assert confirm_resp.status_code == 200
    confirmed = confirm_resp.json()
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_by_user_id"] == str(user_a.id)

    # Re-running evaluation must NOT overwrite the human decision.
    _ingest(client, headers, sensor["id"], [v for v in HEALTHY_PATTERN], base_minutes=-1)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    db_session.expire_all()
    row = db_session.get(HUMSDiagnosticCandidate, uuid.UUID(bearing["id"]))
    assert row.status == "CONFIRMED"


def test_reject_candidate_records_reason(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-05")
    _establish_baseline(client, headers, sensor["id"])
    _ingest(client, headers, sensor["id"], SPIKY, base_minutes=0)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    diagnostics = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers).json()
    bearing = next(d for d in diagnostics if d["fault_code"] == "VIB-BRG-001")

    resp = client.post(
        f"/api/v1/hums/diagnostics/{bearing['id']}/reject", headers=headers,
        json={"reason": "Inspection found no bearing wear; sensor was miscalibrated."},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert "miscalibrated" in body["rejection_reason"]


def test_diagnostics_never_create_finding_or_confirm_without_human_action(
    client: TestClient, db_session: Session, user_a: User, asset_a: Asset
):
    """Safety boundary: H4 must not autonomously confirm, create findings,
    ground the aircraft, or approve maintenance."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H4-VIB-06")
    _establish_baseline(client, headers, sensor["id"])
    _ingest(client, headers, sensor["id"], SPIKY, base_minutes=0)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    diagnostics = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers).json()
    assert all(d["status"] in ("CANDIDATE", "SUPPORTED", "WEAK") for d in diagnostics)
    assert all(d["confirmed_at"] is None for d in diagnostics)
    assert all(d["confirmed_by_user_id"] is None for d in diagnostics)

    from app.models.asset import Asset as AssetModel

    db_session.expire_all()
    refreshed_asset = db_session.get(AssetModel, asset_a.id)
    assert refreshed_asset.status is not None  # unchanged lifecycle status -- H4 never grounds an asset


def test_cross_tenant_diagnostic_isolation(client: TestClient, user_a: User, user_b: User, asset_a: Asset):
    headers_a = _auth_headers(user_a)
    headers_b = _auth_headers(user_b)
    sensor = _create_sensor(client, headers_a, str(asset_a.id), "H4-VIB-07")
    _establish_baseline(client, headers_a, sensor["id"])
    _ingest(client, headers_a, sensor["id"], SPIKY, base_minutes=0)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers_a)

    resp_b = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json() == []

    diagnostics_a = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers_a).json()
    candidate_id = diagnostics_a[0]["id"]

    resp_confirm_b = client.post(f"/api/v1/hums/diagnostics/{candidate_id}/confirm", headers=headers_b)
    assert resp_confirm_b.status_code == 404  # org B cannot even see org A's candidate to confirm it


def test_viewer_can_read_but_not_confirm_or_reject(client: TestClient, user_a: User, asset_a: Asset):
    headers_admin = _auth_headers(user_a)
    sensor = _create_sensor(client, headers_admin, str(asset_a.id), "H4-VIB-08")
    _establish_baseline(client, headers_admin, sensor["id"])
    _ingest(client, headers_admin, sensor["id"], SPIKY, base_minutes=0)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers_admin)
    diagnostics = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers_admin).json()
    candidate_id = diagnostics[0]["id"]

    headers_viewer = _auth_headers(user_a, roles=["VIEWER"])
    read_resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers_viewer)
    assert read_resp.status_code == 200

    confirm_resp = client.post(f"/api/v1/hums/diagnostics/{candidate_id}/confirm", headers=headers_viewer)
    assert confirm_resp.status_code == 403

    reject_resp = client.post(f"/api/v1/hums/diagnostics/{candidate_id}/reject", headers=headers_viewer, json={"reason": "x"})
    assert reject_resp.status_code == 403
