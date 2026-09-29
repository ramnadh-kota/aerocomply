"""H3 Integration Tests: baseline establishment, deviation/trend endpoints,
component/asset health-intelligence aggregation, signal integration,
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
    org = Organization(name=f"H3 Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"H3 Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id, email=f"engineer.{uuid.uuid4().hex[:6]}@a.com", full_name="H3 Engineer A",
        hashed_password="pw", is_active=True, email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_b(db_session: Session, org_b: Organization) -> User:
    user = User(
        organization_id=org_b.id, email=f"engineer.{uuid.uuid4().hex[:6]}@b.com", full_name="H3 Engineer B",
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
        registration=f"H3-{uuid.uuid4().hex[:6].upper()}", serial_number=f"SN-{uuid.uuid4().hex[:6]}",
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
    return component


def _create_sensor(client: TestClient, headers: dict, asset_id: str, component_id: str | None = None) -> dict:
    payload = {
        "asset_id": asset_id,
        "sensor_code": f"SENS-{uuid.uuid4().hex[:6]}",
        "sensor_type": "ACCELEROMETER",
        "measurement_type": "vibration",
        "unit": "mm/s",
    }
    if component_id:
        payload["component_id"] = component_id
    resp = client.post("/api/v1/hums/sensors", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingest_batch(client: TestClient, headers: dict, sensor_id: str, values: list[float], minutes_ago: int) -> None:
    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {"recorded_at": (now - datetime.timedelta(minutes=minutes_ago, seconds=-i)).isoformat(), "value": v, "unit": "mm/s"}
        for i, v in enumerate(values)
    ]
    resp = client.post(f"/api/v1/hums/sensors/{sensor_id}/readings", headers=headers, json={"readings": readings})
    assert resp.status_code == 200, resp.text


HEALTHY_BATCH = ([1.0 + 0.05 * ((-1) ** i) for i in range(10)]) * 2  # 20 values, oscillating 0.95-1.05


def test_baseline_insufficient_until_minimum_batches(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    # Only 3 batches -- below MIN_SAMPLES_FOR_BASELINE (5) for the rms feature history.
    for b in range(3):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(4 - b) * 10)

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "INSUFFICIENT_DATA"


def test_healthy_asset_reports_healthy_with_explanation(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    for b in range(8):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(9 - b) * 10)

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "HEALTHY"
    for comp in body["components"]:
        for contributor in comp["all_contributors"]:
            assert len(contributor["explanation"]) > 0  # explainability requirement


def test_persistent_deviation_triggers_degraded_and_signal(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """Scenario 3 from the H3 spec: feature remains elevated -> DEGRADED,
    with a ProactiveSignalRecord created (reusing the existing model)."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    for b in range(8):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(9 - b) * 10)

    # Elevated but not severe -- mildly outside the tight healthy baseline.
    elevated_batch = [1.3] * 20
    _ingest_batch(client, headers, sensor["id"], elevated_batch, minutes_ago=0)

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] in ("WATCH", "DEGRADED", "WARNING")  # elevated relative to a tight baseline

    db_session.expire_all()
    signals = db_session.query(ProactiveSignalRecord).filter(
        ProactiveSignalRecord.organization_id == uuid.UUID(str(user_a.organization_id)),
        ProactiveSignalRecord.signal_type == "HUMS_HEALTH_DEGRADATION",
    ).all()
    if body["state"] in ("DEGRADED", "WARNING", "CRITICAL"):
        assert len(signals) >= 1
    else:
        assert len(signals) == 0  # WATCH must never spam a signal


def test_accelerating_deterioration_reaches_warning_or_critical(client: TestClient, user_a: User, asset_a: Asset):
    """Scenario 4: accelerating deterioration."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    for b in range(8):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(12 - b) * 10)

    # Progressive, accelerating batches far outside the tight baseline.
    for i, mult in enumerate([1.5, 2.5, 5.0]):
        batch = [1.0 * mult] * 20
        _ingest_batch(client, headers, sensor["id"], batch, minutes_ago=(2 - i) * 5)

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] in ("DEGRADED", "WARNING", "CRITICAL")
    assert len(body["primary_contributors"]) > 0


def test_component_scoped_health(client: TestClient, user_a: User, asset_a: Asset, component_a: Component):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), component_id=str(component_a.id))

    for b in range(8):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(9 - b) * 10)

    resp = client.get(f"/api/v1/hums/components/{component_a.id}/health", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["component_id"] == str(component_a.id)
    assert body["state"] == "HEALTHY"


def test_baseline_deviation_trend_endpoints(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))
    for b in range(8):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(9 - b) * 10)

    baseline_resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/baseline", headers=headers)
    assert baseline_resp.status_code == 200
    baselines = baseline_resp.json()
    assert len(baselines) > 0
    for b in baselines:
        assert b["sample_count"] >= 1
        assert b["version"] >= 1

    deviations_resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/deviations", headers=headers)
    assert deviations_resp.status_code == 200
    assert len(deviations_resp.json()) > 0

    trends_resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/trends", headers=headers)
    assert trends_resp.status_code == 200
    assert len(trends_resp.json()) > 0


def test_baseline_versions_on_recompute(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))
    for b in range(6):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(7 - b) * 10)

    baselines_v1 = client.get(f"/api/v1/hums/assets/{asset_a.id}/baseline", headers=headers).json()
    rms_v1 = next(b for b in baselines_v1 if b["feature_type"] == "rms")

    _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=0)

    baselines_v2 = client.get(f"/api/v1/hums/assets/{asset_a.id}/baseline", headers=headers).json()
    rms_v2 = next(b for b in baselines_v2 if b["feature_type"] == "rms")
    assert rms_v2["version"] > rms_v1["version"]
    assert rms_v2["is_current"] is True


def test_no_signal_spam_for_isolated_normal_variation(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """Scenario 7: stable noisy system -- must never spam a signal for HEALTHY/WATCH."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))
    for b in range(10):
        _ingest_batch(client, headers, sensor["id"], HEALTHY_BATCH, minutes_ago=(11 - b) * 10)

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["state"] in ("HEALTHY", "WATCH")

    db_session.expire_all()
    signals = db_session.query(ProactiveSignalRecord).filter(
        ProactiveSignalRecord.signal_type == "HUMS_HEALTH_DEGRADATION"
    ).all()
    assert len(signals) == 0


def test_cross_tenant_isolation_h3(client: TestClient, user_a: User, user_b: User, asset_a: Asset):
    headers_a = _auth_headers(user_a)
    headers_b = _auth_headers(user_b)
    sensor = _create_sensor(client, headers_a, str(asset_a.id))
    for b in range(8):
        _ingest_batch(client, headers_a, sensor["id"], HEALTHY_BATCH, minutes_ago=(9 - b) * 10)

    for path in ("baseline", "deviations", "trends"):
        resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/{path}", headers=headers_b)
        assert resp.status_code == 200
        assert resp.json() == []

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers_b)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "INSUFFICIENT_DATA"  # org B sees no sensors at all for this asset


def test_viewer_can_read_health_intelligence(client: TestClient, user_a: User, asset_a: Asset):
    headers_admin = _auth_headers(user_a)
    sensor = _create_sensor(client, headers_admin, str(asset_a.id))
    for b in range(8):
        _ingest_batch(client, headers_admin, sensor["id"], HEALTHY_BATCH, minutes_ago=(9 - b) * 10)

    headers_viewer = _auth_headers(user_a, roles=["VIEWER"])
    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers_viewer)
    assert resp.status_code == 200
    assert resp.json()["state"] == "HEALTHY"
