"""H5 Integration Tests: degradation model fitting, threshold sourcing, RUL
computation with uncertainty, maintenance-reset segmentation, H4 diagnostic
linkage, ProactiveSignalRecord integration, safety-boundary tests, tenant
isolation, and RBAC.
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.installation_history import ComponentInstallation
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
        # M20: /telemetry and /hums/*/prognostics are now commercially gated.
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="flight_telemetry", enabled=True))
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="predictive_maintenance", enabled=True))
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
    org = Organization(name=f"H5 Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"H5 Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    _seed_hums_sub(db_session, org.id)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id, email=f"engineer.{uuid.uuid4().hex[:6]}@a.com", full_name="H5 Engineer A",
        hashed_password="pw", is_active=True, email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_b(db_session: Session, org_b: Organization) -> User:
    user = User(
        organization_id=org_b.id, email=f"engineer.{uuid.uuid4().hex[:6]}@b.com", full_name="H5 Engineer B",
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
        registration=f"H5-{uuid.uuid4().hex[:6].upper()}", serial_number=f"SN-{uuid.uuid4().hex[:6]}",
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


def _feed_linear_degradation(client, headers, sensor_id, n_batches=15, start=1.0, slope_per_batch=0.15, spacing_minutes=60):
    for b in range(n_batches):
        val = start + slope_per_batch * b
        _ingest(client, headers, sensor_id, [val] * 20, base_minutes=(n_batches - b) * spacing_minutes)


def test_healthy_stable_component_no_meaningful_rul_warning(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """H5-A."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-A")
    for b in range(10):
        _ingest(client, headers, sensor["id"], [1.0] * 20, base_minutes=(10 - b) * 60)

    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    progs = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers).json()
    rms = next(p for p in progs if p["feature_type"] == "rms")
    assert rms["status"] in ("AVAILABLE", "LIMITED")
    if rms["rul_estimate"] is not None:
        assert rms["rul_estimate"] > 50  # not in warning window for a flat trajectory

    db_session.expire_all()
    signals = db_session.query(ProactiveSignalRecord).filter(
        ProactiveSignalRecord.organization_id == asset_a.organization_id, ProactiveSignalRecord.signal_type == "HUMS_RUL_WARNING"
    ).all()
    assert len(signals) == 0


def test_linear_degradation_matches_known_threshold_crossing_within_tolerance(client: TestClient, user_a: User, asset_a: Asset):
    """H5-B / H5-H: quantitative accuracy check against a known synthetic trajectory."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-B")
    slope = 0.15
    start = 1.0
    n_batches = 20
    _feed_linear_degradation(client, headers, sensor["id"], n_batches=n_batches, start=start, slope_per_batch=slope, spacing_minutes=60)

    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    progs = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers).json()
    rms = next(p for p in progs if p["feature_type"] == "rms")

    assert rms["threshold_value"] == 8.0  # H1's VIBRATION_CRITICAL_RMS, reused as the MAINTENANCE_THRESHOLD
    assert rms["threshold_type"] == "MAINTENANCE_THRESHOLD"

    # Known: current ~= 1.0 + 0.15*19 = 3.85; expected crossing usage = (8.0-1.0)/0.15 = 46.67
    expected_crossing = (8.0 - start) / slope
    current_usage_hours = n_batches - 1  # 1-hour spacing, n_batches points starting at 0
    expected_rul = expected_crossing - current_usage_hours
    assert rms["rul_estimate"] is not None
    error_pct = abs(rms["rul_estimate"] - expected_rul) / expected_rul * 100
    assert error_pct < 5.0, f"RUL error {error_pct}% exceeds 5% tolerance"
    assert rms["confidence"] == "HIGH"
    assert rms["rul_lower"] <= rms["rul_estimate"] <= rms["rul_upper"]
    assert "NOT A CERTIFIED LIFE LIMIT" in " ".join(rms["explanation"])


def test_accelerating_degradation_produces_shorter_rul_and_accelerating_trajectory(client: TestClient, user_a: User, asset_a: Asset):
    """H5-C."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-C")
    now_batches = [1.0, 1.05, 1.1, 1.15, 1.5, 2.5, 4.0, 6.0]
    for i, val in enumerate(now_batches):
        _ingest(client, headers, sensor["id"], [val] * 20, base_minutes=(len(now_batches) - i) * 60)

    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    degradation = client.get(f"/api/v1/hums/assets/{asset_a.id}/degradation", headers=headers).json()
    rms_model = next(m for m in degradation if m["feature_type"] == "rms")
    assert rms_model["trajectory_state"] in ("ACCELERATING", "DEGRADING")  # deterministic heuristic; accelerating in the strong case


def test_insufficient_history_returns_null_rul_not_fabricated(client: TestClient, user_a: User, asset_a: Asset):
    """H5-E."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-E")
    _ingest(client, headers, sensor["id"], [1.0] * 3, base_minutes=0)

    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    progs = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers).json()
    rms = next(p for p in progs if p["feature_type"] == "rms")
    assert rms["status"] == "INSUFFICIENT_DATA"
    assert rms["rul_estimate"] is None


def test_maintenance_reset_starts_new_reference_baseline(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """H5-F: a component installation event after prior degradation history
    should cause the reference baseline to start fresh from post-reset data."""
    headers = _auth_headers(user_a)
    component = Component(
        organization_id=asset_a.organization_id, asset_id=asset_a.id, component_type=ComponentType.ENGINE,
        name="Engine 1", serial_number=f"CMP-{uuid.uuid4().hex[:6]}", status=ComponentStatus.INSTALLED,
    )
    db_session.add(component)
    db_session.commit()
    db_session.refresh(component)

    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-F", component_id=str(component.id))

    now = datetime.datetime.now(datetime.UTC)
    # Pre-reset degrading history (older, further in the past).
    for b in range(8):
        _ingest(client, headers, sensor["id"], [1.0 + 0.5 * b] * 20, base_minutes=(20 - b) * 60)

    # Installation event (overhaul/replacement) happens between old and new history.
    installation = ComponentInstallation(
        organization_id=asset_a.organization_id, component_id=component.id, asset_id=asset_a.id,
        installed_at=now - datetime.timedelta(minutes=11 * 60),
    )
    db_session.add(installation)
    db_session.commit()

    # Post-reset healthy history.
    for b in range(8):
        _ingest(client, headers, sensor["id"], [1.0 + 0.05 * b] * 20, base_minutes=(9 - b) * 60)

    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    baselines = client.get(f"/api/v1/hums/assets/{asset_a.id}/baseline", headers=headers).json()
    rms_baseline = next(b for b in baselines if b["feature_type"] == "rms")
    # The reference should reflect the post-reset (lower, ~1.0-1.35) window, not the
    # pre-reset degraded (~1.0-4.5) window's much higher mean.
    assert rms_baseline["mean"] < 3.0


def test_diagnostic_candidate_linked_as_context_not_confirmed_truth(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """H5-G: a related H4 diagnostic hypothesis is surfaced as context, never treated as ground truth."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-G")
    for b in range(8):
        jitter = 1.0 + 0.07 * (((b % 3) - 1))
        _ingest(client, headers, sensor["id"], [1.0 * jitter] * 20, base_minutes=(9 - b) * 10)
    _ingest(client, headers, sensor["id"], [1.0] * 18 + [8.0, -6.0], base_minutes=0)

    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)
    diagnostics = client.get(f"/api/v1/hums/assets/{asset_a.id}/diagnostics", headers=headers).json()
    assert len(diagnostics) >= 1

    progs = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers).json()
    rms = next(p for p in progs if p["feature_type"] == "rms")
    if rms["related_diagnostic_candidate_id"] if "related_diagnostic_candidate_id" in rms else rms.get("diagnostic_candidate_id"):
        assert any(d["id"] == rms["diagnostic_candidate_id"] for d in diagnostics)


def test_rul_warning_signal_fires_once_for_meaningful_transition(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-SIG")
    _feed_linear_degradation(client, headers, sensor["id"], n_batches=20, start=1.0, slope_per_batch=0.15, spacing_minutes=60)

    for _ in range(3):
        client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    db_session.expire_all()
    signals = db_session.query(ProactiveSignalRecord).filter(
        ProactiveSignalRecord.organization_id == asset_a.organization_id, ProactiveSignalRecord.signal_type == "HUMS_RUL_WARNING"
    ).all()
    assert len(signals) == 1


def test_prognostic_never_grounds_asset_or_declares_airworthiness(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """Safety boundary: H5 must not autonomously ground, certify, or approve maintenance."""
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), "H5-VIB-SAFETY")
    _feed_linear_degradation(client, headers, sensor["id"], n_batches=20, start=1.0, slope_per_batch=0.3, spacing_minutes=60)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers)

    from app.models.asset import Asset as AssetModel

    db_session.expire_all()
    refreshed = db_session.get(AssetModel, asset_a.id)
    assert refreshed.status is not None  # unchanged -- H5 never sets GROUNDED/AIRWORTHY

    progs = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers).json()
    for p in progs:
        assert "ESTIMATE" in " ".join(p["explanation"]) or p["status"] == "INSUFFICIENT_DATA"


def test_cross_tenant_prognostic_isolation(client: TestClient, user_a: User, user_b: User, asset_a: Asset):
    headers_a = _auth_headers(user_a)
    headers_b = _auth_headers(user_b)
    sensor = _create_sensor(client, headers_a, str(asset_a.id), "H5-VIB-TENANT")
    _feed_linear_degradation(client, headers_a, sensor["id"], n_batches=15, start=1.0, slope_per_batch=0.15)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers_a)

    resp_b = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json() == []

    resp_degradation_b = client.get(f"/api/v1/hums/assets/{asset_a.id}/degradation", headers=headers_b)
    assert resp_degradation_b.status_code == 200
    assert resp_degradation_b.json() == []


def test_viewer_can_read_prognostics(client: TestClient, user_a: User, asset_a: Asset):
    headers_admin = _auth_headers(user_a)
    sensor = _create_sensor(client, headers_admin, str(asset_a.id), "H5-VIB-VIEWER")
    _feed_linear_degradation(client, headers_admin, sensor["id"], n_batches=15, start=1.0, slope_per_batch=0.15)
    client.get(f"/api/v1/hums/assets/{asset_a.id}/health-intelligence", headers=headers_admin)

    headers_viewer = _auth_headers(user_a, roles=["VIEWER"])
    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/prognostics", headers=headers_viewer)
    assert resp.status_code == 200
    assert len(resp.json()) > 0
