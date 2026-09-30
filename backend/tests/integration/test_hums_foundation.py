"""H1 Integration Tests: HUMS foundation vertical slice.

Verifies the pathway Sensor -> Reading -> Feature (RMS) -> Exceedance ->
Finding -> Evidence -> Signal, plus tenant isolation and RBAC.
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support.tokens import mint_token as create_access_token
from app.models.asset import Asset, AssetType
from app.models.evidence import Evidence
from app.models.finding import Finding
from app.models.hums import HUMSExceedance, HUMSSensor, HUMSSensorReading
from app.models.organization import Organization
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.user import User


def _auth_headers(user: User, roles: list[str] | None = None) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        roles=roles or ["ORG_ADMIN"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
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
    org = Organization(name=f"HUMS Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"HUMS Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id,
        email=f"engineer.{uuid.uuid4().hex[:6]}@a.com",
        full_name="HUMS Engineer A",
        hashed_password="pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_b(db_session: Session, org_b: Organization) -> User:
    user = User(
        organization_id=org_b.id,
        email=f"engineer.{uuid.uuid4().hex[:6]}@b.com",
        full_name="HUMS Engineer B",
        hashed_password="pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def asset_a(db_session: Session, org_a: Organization) -> Asset:
    asset = Asset(
        organization_id=org_a.id,
        asset_type=AssetType.DRONE,
        registration=f"HUMS-{uuid.uuid4().hex[:6].upper()}",
        serial_number=f"SN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _create_sensor(client: TestClient, headers: dict, asset_id: str) -> dict:
    resp = client.post(
        "/api/v1/hums/sensors",
        headers=headers,
        json={
            "asset_id": asset_id,
            "sensor_code": "GBX-VIB-01",
            "sensor_type": "ACCELEROMETER",
            "measurement_type": "vibration",
            "unit": "mm/s",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_sensor_creation_and_readings_below_threshold_report_healthy(
    client: TestClient, org_a: Organization, user_a: User, asset_a: Asset
):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {"recorded_at": (now - datetime.timedelta(seconds=i)).isoformat(), "value": 1.5, "unit": "mm/s"}
        for i in range(10)
    ]
    resp = client.post(
        f"/api/v1/hums/sensors/{sensor['id']}/readings",
        headers=headers,
        json={"readings": readings, "ingestion_batch": "batch-1"},
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 10

    health = client.get(f"/api/v1/hums/assets/{asset_a.id}/health", headers=headers)
    assert health.status_code == 200
    body = health.json()
    assert body["overall_status"] == "HEALTHY"
    assert body["components"][0]["status"] == "HEALTHY"
    assert body["components"][0]["health_score"] is not None


def test_vibration_exceedance_creates_full_evidence_chain(
    client: TestClient, db_session: Session, org_a: Organization, user_a: User, asset_a: Asset
):
    """Scenario 2/4 from the HUMS spec: sensor -> feature -> anomaly ->
    finding -> evidence -> signal, all traceable back to the raw readings.
    """
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {"recorded_at": (now - datetime.timedelta(seconds=i)).isoformat(), "value": 9.5, "unit": "mm/s"}
        for i in range(10)
    ]
    resp = client.post(
        f"/api/v1/hums/sensors/{sensor['id']}/readings",
        headers=headers,
        json={"readings": readings},
    )
    assert resp.status_code == 200, resp.text

    exceedances = client.get(f"/api/v1/hums/assets/{asset_a.id}/exceedances", headers=headers)
    assert exceedances.status_code == 200
    ex_list = exceedances.json()
    assert len(ex_list) == 1
    assert ex_list[0]["severity"] == "CRITICAL"
    finding_id = ex_list[0]["finding_id"]
    assert finding_id is not None

    db_session.expire_all()
    finding = db_session.get(Finding, uuid.UUID(finding_id))
    assert finding is not None
    assert finding.organization_id == org_a.id

    evidence = db_session.query(Evidence).filter(Evidence.finding_id == finding.id).all()
    assert len(evidence) == 1
    assert evidence[0].provenance["sensor_id"] == sensor["id"]

    signal = (
        db_session.query(ProactiveSignalRecord)
        .filter(
            ProactiveSignalRecord.organization_id == org_a.id,
            ProactiveSignalRecord.signal_type == "HUMS_VIBRATION_EXCEEDANCE",
        )
        .one_or_none()
    )
    assert signal is not None
    assert signal.asset_id == asset_a.id

    health = client.get(f"/api/v1/hums/assets/{asset_a.id}/health", headers=headers)
    assert health.json()["overall_status"] == "CRITICAL"


def test_insufficient_readings_reports_insufficient_data_not_fabricated_score(
    client: TestClient, user_a: User, asset_a: Asset
):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    now = datetime.datetime.now(datetime.UTC)
    resp = client.post(
        f"/api/v1/hums/sensors/{sensor['id']}/readings",
        headers=headers,
        json={"readings": [{"recorded_at": now.isoformat(), "value": 2.0, "unit": "mm/s"}]},
    )
    assert resp.status_code == 200

    health = client.get(f"/api/v1/hums/assets/{asset_a.id}/health", headers=headers)
    body = health.json()
    assert body["components"][0]["status"] == "INSUFFICIENT_DATA"
    assert body["components"][0]["health_score"] is None


def test_cross_tenant_isolation(
    client: TestClient, user_a: User, user_b: User, asset_a: Asset
):
    headers_a = _auth_headers(user_a)
    headers_b = _auth_headers(user_b)

    sensor = _create_sensor(client, headers_a, str(asset_a.id))

    # org_b cannot see org_a's sensors
    resp = client.get("/api/v1/hums/sensors", headers=headers_b, params={"asset_id": str(asset_a.id)})
    assert resp.status_code == 200
    assert resp.json() == []

    # org_b cannot post readings to org_a's sensor (sensor lookup is tenant-scoped -> 404)
    resp = client.post(
        f"/api/v1/hums/sensors/{sensor['id']}/readings",
        headers=headers_b,
        json={"readings": [{"recorded_at": datetime.datetime.now(datetime.UTC).isoformat(), "value": 1.0, "unit": "mm/s"}]},
    )
    assert resp.status_code == 404


def test_viewer_role_cannot_write_hums_data(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a, roles=["VIEWER"])
    resp = client.post(
        "/api/v1/hums/sensors",
        headers=headers,
        json={
            "asset_id": str(asset_a.id),
            "sensor_code": "GBX-VIB-02",
            "sensor_type": "ACCELEROMETER",
            "measurement_type": "vibration",
            "unit": "mm/s",
        },
    )
    assert resp.status_code == 403
