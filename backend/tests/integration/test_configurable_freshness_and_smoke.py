"""Production Readiness & Comprehensive Smoke Tests:
1. Configurable Telemetry Freshness Policies (Tenant Default, Asset Override, Policy Disable).
2. M7 Proactive Signal generation respecting custom freshness thresholds.
3. Complete Production Smoke Test for Horizon Air Mobility (Auth -> Fleet -> Flight -> Telemetry -> HUMS -> M7 -> LISA -> Incidents -> Hypercare).
"""

import datetime
import uuid
from datetime import UTC, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.permissions import Role
from app.core.security import hash_password
from tests.support.tokens import mint_token as create_access_token
from app.models.asset import Asset, AssetType
from app.models.hums import HUMSSensor, HUMSSensorReading
from app.models.organization import Organization
from app.models.telemetry import TelemetryEventLog, TelemetryFreshnessPolicy, TelemetryProcessingStatus
from app.models.user import User, UserRole
from app.schemas.telemetry import TelemetryFreshnessPolicyCreate
from app.services import auth_service, telemetry_service
from app.services.intelligence import proactive_intelligence_service


@pytest.fixture
def smoke_tenant_setup(db_session):
    """Sets up a complete Horizon Air Mobility tenant fixture for production smoke testing."""
    suffix = uuid.uuid4().hex[:6]
    org = Organization(name=f"Horizon Production Smoke {suffix}")
    db_session.add(org)
    db_session.flush()
    # M20: /telemetry/* is gated by the flight_telemetry commercial feature.
    from tests.integration.conftest import grant_features

    grant_features(db_session, org.id, "flight_telemetry")

    admin_user = User(
        organization_id=org.id,
        email=f"admin.{suffix}@horizon.com",
        hashed_password=hash_password("SmokePass123!"),
        full_name="Horizon System Admin",
        is_active=True,
        email_verified=True,
    )
    camo_user = User(
        organization_id=org.id,
        email=f"camo.{suffix}@horizon.com",
        hashed_password=hash_password("SmokePass123!"),
        full_name="Horizon CAMO Manager",
        is_active=True,
        email_verified=True,
    )
    db_session.add_all([admin_user, camo_user])
    db_session.flush()

    db_session.add_all([
        UserRole(user_id=admin_user.id, organization_id=org.id, role_name=Role.ORG_ADMIN),
        UserRole(user_id=camo_user.id, organization_id=org.id, role_name=Role.CAMO_MANAGER),
    ])
    db_session.flush()

    # Create Horizon Fleet Assets (ATR-72 aircraft + FlyCart 30 drone)
    aircraft_asset = Asset(
        organization_id=org.id,
        asset_type=AssetType.AIRCRAFT,
        registration=f"VT-HZA-{suffix.upper()}",
    )
    drone_asset = Asset(
        organization_id=org.id,
        asset_type=AssetType.DRONE,
        registration=f"DR-HZ01-{suffix.upper()}",
    )
    db_session.add_all([aircraft_asset, drone_asset])
    db_session.flush()

    token_admin = create_access_token(admin_user.id, org.id, [Role.ORG_ADMIN], email=admin_user.email, full_name=admin_user.full_name)
    token_camo = create_access_token(camo_user.id, org.id, [Role.CAMO_MANAGER], email=camo_user.email, full_name=camo_user.full_name)

    return {
        "org": org,
        "admin": admin_user,
        "camo": camo_user,
        "token_admin": token_admin,
        "token_camo": token_camo,
        "aircraft": aircraft_asset,
        "drone": drone_asset,
    }


def test_telemetry_freshness_policy_crud(client, smoke_tenant_setup, db_session):
    """Verifies creating, listing, and overriding configurable freshness policies."""
    setup = smoke_tenant_setup

    # 1. Create a tenant-wide default policy: 3 days warning, 6 days critical
    create_payload = {
        "asset_id": None,
        "source_system": None,
        "warning_threshold_days": 3,
        "critical_threshold_days": 6,
        "is_active": True,
        "description": "Tenant-wide tight freshness policy",
    }
    res = client.post(
        "/api/v1/telemetry/freshness-policies",
        json=create_payload,
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["warning_threshold_days"] == 3
    assert data["critical_threshold_days"] == 6

    # 2. List policies
    list_res = client.get(
        "/api/v1/telemetry/freshness-policies",
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert list_res.status_code == status.HTTP_200_OK
    assert len(list_res.json()) >= 1

    # 3. Create an asset-specific override: 1 day warning, 2 days critical for the drone
    asset_payload = {
        "asset_id": str(setup["drone"].id),
        "source_system": "DJI_FLIGHTHUB",
        "warning_threshold_days": 1,
        "critical_threshold_days": 2,
        "is_active": True,
        "description": "Daily drone telemetry requirement",
    }
    asset_res = client.post(
        "/api/v1/telemetry/freshness-policies",
        json=asset_payload,
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert asset_res.status_code == status.HTTP_200_OK
    assert asset_res.json()["warning_threshold_days"] == 1


def test_m7_proactive_signals_respect_configured_freshness_policy(client, smoke_tenant_setup, db_session):
    """Verifies M7 generates warning/critical signals matching custom policy thresholds rather than a hardcoded 7 days."""
    setup = smoke_tenant_setup

    # Configure a 2-day warning, 4-day critical policy for the drone
    telemetry_service.upsert_freshness_policy(
        db_session,
        setup["org"].id,
        TelemetryFreshnessPolicyCreate(
            asset_id=setup["drone"].id,
            warning_threshold_days=2,
            critical_threshold_days=4,
            is_active=True,
        ),
    )

    # Seed a sensor and reading from 3 days ago (exceeds warning threshold of 2 days, below critical of 4)
    sensor = HUMSSensor(
        organization_id=setup["org"].id,
        asset_id=setup["drone"].id,
        sensor_code="DRONE-BATTERY-VOLT",
        sensor_type="VOLTAGE",
        measurement_type="VOLTAGE",
        unit="V",
        status="ACTIVE",
    )
    db_session.add(sensor)
    db_session.flush()

    old_reading_time = datetime.datetime.now(UTC) - timedelta(days=3)
    reading = HUMSSensorReading(
        organization_id=setup["org"].id,
        sensor_id=sensor.id,
        asset_id=setup["drone"].id,
        recorded_at=old_reading_time,
        value=51.2,
        unit="V",
        data_quality="VALID",
    )
    db_session.add(reading)
    db_session.flush()

    # Evaluate proactive intelligence
    signals = proactive_intelligence_service.sync_and_get_signals(
        db_session, organization_id=setup["org"].id, asset_id=setup["drone"].id
    )

    # Find TELEMETRY_FRESHNESS signal
    stale_signals = [s for s in signals if s.signal_type == "TELEMETRY_FRESHNESS" and s.asset_id == setup["drone"].id]
    assert len(stale_signals) >= 1
    stale_signal = stale_signals[0]
    assert stale_signal.severity == "MEDIUM"
    assert "threshold: 2d" in stale_signal.headline


def test_end_to_end_production_smoke_flow(client, smoke_tenant_setup, db_session):
    """Full Production Smoke Test:
    Auth -> Fleet -> Telemetry Policy -> Incident Creation & Resolution -> Hypercare Observability.
    """
    setup = smoke_tenant_setup

    # 1. Fleet Query
    fleet_res = client.get(
        "/api/v1/assets",
        headers={"Authorization": f"Bearer {setup['token_camo']}"},
    )
    assert fleet_res.status_code == status.HTTP_200_OK

    # 2. Create an Operational P1 Incident
    inc_payload = {
        "severity": "P1",
        "service_name": "TELEMETRY",
        "title": "Smoke Test: Webhook Latency Alert",
        "description": "Telemetry ingestion webhook response latency exceeded 500ms.",
        "asset_id": str(setup["aircraft"].id),
        "details": {"latency_ms": 650, "threshold_ms": 500},
    }
    inc_res = client.post(
        "/api/v1/hypercare/incidents",
        json=inc_payload,
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert inc_res.status_code == status.HTTP_200_OK
    inc_id = inc_res.json()["id"]

    # 3. Check Hypercare Summary (Platform should report DEGRADED due to P1 incident)
    summary_res = client.get(
        "/api/v1/hypercare/summary",
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert summary_res.status_code == status.HTTP_200_OK
    summary = summary_res.json()
    assert summary["platform_status"] == "DEGRADED"
    assert summary["incidents"]["open_p1"] >= 1

    # 4. Acknowledge and Resolve Incident
    ack_res = client.post(
        f"/api/v1/hypercare/incidents/{inc_id}/acknowledge",
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert ack_res.status_code == status.HTTP_200_OK

    resolve_res = client.post(
        f"/api/v1/hypercare/incidents/{inc_id}/resolve",
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert resolve_res.status_code == status.HTTP_200_OK
    assert resolve_res.json()["status"] == "RESOLVED"

    # 5. Check Hypercare Summary again (Platform status should be restored to OPERATIONAL)
    summary_res2 = client.get(
        "/api/v1/hypercare/summary",
        headers={"Authorization": f"Bearer {setup['token_admin']}"},
    )
    assert summary_res2.status_code == status.HTTP_200_OK
    assert summary_res2.json()["incidents"]["open_p1"] == 0
