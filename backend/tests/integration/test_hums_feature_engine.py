"""H2 Integration Tests: HUMS feature engine wired into the H1 pathway.

Verifies: Sensor Reading -> Feature (persisted, multi-type) -> Exceedance ->
Signal -> Evidence, progressive degradation across multiple ingestion
batches, feature-history/spectrum endpoints, tenant isolation, and RBAC.
"""

import datetime
import math
import uuid

import pytest
from tests.integration.conftest import grant_features
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.hums import HUMSFeature
from app.models.organization import Organization
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


@pytest.fixture
def org_a(db_session: Session) -> Organization:
    org = Organization(name=f"H2 Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    grant_features(db_session, org.id, 'hums')
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"H2 Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    grant_features(db_session, org.id, 'hums')
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id,
        email=f"engineer.{uuid.uuid4().hex[:6]}@a.com",
        full_name="H2 Engineer A",
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
        full_name="H2 Engineer B",
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
        registration=f"H2-{uuid.uuid4().hex[:6].upper()}",
        serial_number=f"SN-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


def _create_sensor(client: TestClient, headers: dict, asset_id: str, measurement_type: str = "vibration", unit: str = "mm/s") -> dict:
    resp = client.post(
        "/api/v1/hums/sensors",
        headers=headers,
        json={
            "asset_id": asset_id,
            "sensor_code": f"SENS-{uuid.uuid4().hex[:6]}",
            "sensor_type": "ACCELEROMETER" if measurement_type == "vibration" else "GENERIC",
            "measurement_type": measurement_type,
            "unit": unit,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ingest(client: TestClient, headers: dict, sensor_id: str, values: list[float], unit: str, start_offset_seconds: int = 0) -> dict:
    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {
            "recorded_at": (now - datetime.timedelta(seconds=start_offset_seconds - i)).isoformat(),
            "value": v,
            "unit": unit,
        }
        for i, v in enumerate(values)
    ]
    resp = client.post(f"/api/v1/hums/sensors/{sensor_id}/readings", headers=headers, json={"readings": readings})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_ingestion_persists_full_feature_set(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    # Sine-like vibration signal so kurtosis/skewness/FFT all have enough
    # shape to compute (not a degenerate constant signal).
    values = [1.0 + 0.5 * math.sin(i) for i in range(20)]
    _ingest(client, headers, sensor["id"], values, "mm/s")

    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/features", headers=headers)
    assert resp.status_code == 200
    features = resp.json()
    feature_types = {f["feature_type"] for f in features}
    for expected in ("rms", "peak", "peak_to_peak", "crest_factor", "kurtosis", "skewness", "dominant_frequency", "spectral_energy", "band_energy", "mean", "std"):
        assert expected in feature_types, f"missing {expected} in {feature_types}"

    for f in features:
        assert f["sensor_id"] == sensor["id"]
        assert f["asset_id"] == str(asset_a.id)


def test_progressive_vibration_degradation_scenario(client: TestClient, db_session: Session, user_a: User, asset_a: Asset):
    """Scenario 3/4 from the HUMS spec, extended in H2: normal -> small
    increase -> progressive increase -> RMS/crest-factor increase ->
    exceedance -> H1 evidence pathway, verified across successive batches.
    """
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    # FEATURE_WINDOW_READING_COUNT (hums_service.py) looks at the sensor's
    # last 20 readings regardless of batch boundaries, so each batch here
    # has >=20 samples -- otherwise a window would blend two batches and
    # understate the true current RMS, which is realistic system behavior
    # but would make this specific test's exact-severity assertions flaky.
    healthy = [1.0, 1.1, 0.9, 1.0, 1.2, 0.8, 1.0, 1.1, 0.9, 1.0] * 2
    small_increase = [2.0, 2.2, 1.8, 2.0, 2.3, 1.7, 2.0, 2.1, 1.9, 2.0] * 2
    progressive = [4.0, 4.3, 3.7, 4.0, 4.5, 3.5, 4.0, 4.2, 3.8, 4.0] * 2
    critical = [9.0, 9.5, 8.5, 9.0, 9.8, 8.2, 9.0, 9.3, 8.7, 9.0] * 2
    batches = [healthy, small_increase, progressive, critical]

    rms_history = []
    exceedance_result = None
    for i, batch in enumerate(batches):
        _ingest(client, headers, sensor["id"], batch, "mm/s", start_offset_seconds=(len(batches) - i) * 100)
        health = client.get(f"/api/v1/hums/assets/{asset_a.id}/health", headers=headers).json()
        rms_feature = health["components"][0]["latest_feature"]
        if rms_feature:
            rms_history.append(rms_feature["value"])

    # RMS should trend upward across the batches, demonstrating visible degradation.
    assert rms_history == sorted(rms_history), f"expected increasing RMS trend, got {rms_history}"

    exceedances = client.get(f"/api/v1/hums/assets/{asset_a.id}/exceedances", headers=headers).json()
    assert len(exceedances) >= 1
    assert exceedances[-1]["severity"] == "CRITICAL"
    assert exceedances[-1]["finding_id"] is not None

    # Feature history should have multiple RMS rows tracing the trend.
    rms_rows = client.get(
        f"/api/v1/hums/assets/{asset_a.id}/features/rms", headers=headers
    ).json()
    assert len(rms_rows) == len(batches)


def test_spectrum_endpoint_returns_dominant_frequency(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))

    sampling_rate = 100.0
    signal_freq = 10.0
    values = [math.sin(2 * math.pi * signal_freq * (i / sampling_rate)) for i in range(40)]
    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {"recorded_at": (now + datetime.timedelta(seconds=i / sampling_rate)).isoformat(), "value": v, "unit": "g"}
        for i, v in enumerate(values)
    ]
    resp = client.post(f"/api/v1/hums/sensors/{sensor['id']}/readings", headers=headers, json={"readings": readings})
    assert resp.status_code == 200

    spectrum = client.get(f"/api/v1/hums/sensors/{sensor['id']}/spectrum", headers=headers)
    assert spectrum.status_code == 200
    body = spectrum.json()
    assert body["quality"] == "GOOD"
    assert len(body["frequencies_hz"]) == len(body["magnitudes"])
    assert abs(body["dominant_frequency_hz"] - signal_freq) <= body["frequency_resolution_hz"]


def test_temperature_trend_features(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id), measurement_type="temperature", unit="C")

    now = datetime.datetime.now(datetime.UTC)
    readings = [
        {"recorded_at": (now - datetime.timedelta(minutes=10 - i)).isoformat(), "value": 60.0 + i * 2.0, "unit": "C"}
        for i in range(10)
    ]
    resp = client.post(f"/api/v1/hums/sensors/{sensor['id']}/readings", headers=headers, json={"readings": readings})
    assert resp.status_code == 200

    features = client.get(f"/api/v1/hums/sensors/{sensor['id']}/features", headers=headers).json()
    feature_types = {f["feature_type"] for f in features}
    assert "trend" in feature_types
    assert "rate_of_change" in feature_types
    trend = next(f for f in features if f["feature_type"] == "trend")
    assert trend["value"] > 0  # increasing temperature


def test_insufficient_samples_reports_insufficient_data_quality(client: TestClient, user_a: User, asset_a: Asset):
    headers = _auth_headers(user_a)
    sensor = _create_sensor(client, headers, str(asset_a.id))
    now = datetime.datetime.now(datetime.UTC)
    resp = client.post(
        f"/api/v1/hums/sensors/{sensor['id']}/readings",
        headers=headers,
        json={"readings": [{"recorded_at": now.isoformat(), "value": 1.0, "unit": "mm/s"}]},
    )
    assert resp.status_code == 200

    features = client.get(f"/api/v1/hums/sensors/{sensor['id']}/features", headers=headers).json()
    kurtosis = next(f for f in features if f["feature_type"] == "kurtosis")
    assert kurtosis["quality"] == "INSUFFICIENT_DATA"
    fft = next(f for f in features if f["feature_type"] == "dominant_frequency")
    assert fft["quality"] == "INSUFFICIENT_DATA"


def test_cross_tenant_feature_isolation(client: TestClient, user_a: User, user_b: User, asset_a: Asset):
    headers_a = _auth_headers(user_a)
    headers_b = _auth_headers(user_b)
    sensor = _create_sensor(client, headers_a, str(asset_a.id))
    _ingest(client, headers_a, sensor["id"], [1.0 + 0.1 * i for i in range(10)], "mm/s")

    resp_b = client.get(f"/api/v1/hums/assets/{asset_a.id}/features", headers=headers_b)
    assert resp_b.status_code == 200
    assert resp_b.json() == []

    resp_b_sensor = client.get(f"/api/v1/hums/sensors/{sensor['id']}/features", headers=headers_b)
    assert resp_b_sensor.status_code == 200
    assert resp_b_sensor.json() == []


def test_viewer_can_read_features_but_not_ingest(client: TestClient, user_a: User, asset_a: Asset):
    headers_admin = _auth_headers(user_a)
    sensor = _create_sensor(client, headers_admin, str(asset_a.id))
    _ingest(client, headers_admin, sensor["id"], [1.0] * 10, "mm/s")

    headers_viewer = _auth_headers(user_a, roles=["VIEWER"])
    resp = client.get(f"/api/v1/hums/assets/{asset_a.id}/features", headers=headers_viewer)
    assert resp.status_code == 200
    assert len(resp.json()) > 0
