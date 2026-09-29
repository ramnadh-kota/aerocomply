"""M13 Phase 2: Telemetry Ingestion Contract & DJI FlightHub 2 Adapter Integration Tests.

Verifies:
1. Tenant-isolated external asset mapping.
2. HMAC-SHA256 signature verification.
3. Normalized telemetry flight ingestion & utilization accounting.
4. Deterministic idempotency & duplicate-event protection (zero double-counting).
5. Cross-tenant isolation & IDOR prevention.
6. Unmatched asset quarantine without raw state mutation.
7. Battery telemetry & HUMS sensor reading creation.
8. Audit trail logging.
"""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.core.deps import get_db_session
from app.core.security import hash_password
from app.models.asset import Asset
from app.models.battery import Battery
from app.models.flight import Flight
from app.models.hums import HUMSSensor, HUMSSensorReading
from app.models.organization import Organization
from app.models.telemetry import (
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryProcessingStatus,
)
from app.models.user import User, UserRole
from app.schemas.drone_ops import DroneCreateRequest
from app.schemas.telemetry import (
    DJIFlightHubWebhookPayload,
    ExternalAssetMappingCreate,
    NormalizedTelemetryEvent,
    TelemetryBatteryPayload,
    TelemetryFlightPayload,
    TelemetryIngestRequest,
    TelemetryReadingItem,
)
from app.services import asset_service, auth_service, drone_service, flight_service, telemetry_service


@pytest.fixture
def test_tenant_setup(db_session):
    """Creates a dedicated test tenant with an admin user, a drone asset, and a battery."""
    org_suffix = uuid.uuid4().hex[:6]
    org = Organization(
        name=f"Horizon M13 Telemetry Test {org_suffix}",
    )
    db_session.add(org)
    db_session.flush()

    admin_user = User(
        organization_id=org.id,
        email=f"admin_{org_suffix}@horizon.test",
        hashed_password=hash_password("TestPassword123!"),
        full_name="Horizon Test Admin",
        is_active=True,
        email_verified=True,
    )
    db_session.add(admin_user)
    db_session.flush()

    role = UserRole(
        user_id=admin_user.id,
        role_name="ORG_ADMIN",
        organization_id=org.id,
    )
    db_session.add(role)
    db_session.flush()

    drone = drone_service.create_drone(
        db_session,
        organization_id=org.id,
        actor_user_id=admin_user.id,
        registration=f"DR-{org_suffix.upper()}",
        manufacturer="DJI",
        model="DJI FlyCart 30",
        serial_number=f"FC30-TEST-{uuid.uuid4().hex[:4]}",
        facility_id=None,
    )

    battery = Battery(
        organization_id=org.id,
        asset_id=drone.id,
        serial_number=f"TB30-TEST-{uuid.uuid4().hex[:4]}",
        manufacturer="DJI",
        model="TB30 Intelligent Battery",
        cycle_count=10,
        health_percent=98,
        voltage=52000,
    )
    db_session.add(battery)
    db_session.flush()

    return {
        "org": org,
        "admin": admin_user,
        "drone": drone,
        "battery": battery,
    }


def test_external_asset_mapping_tenant_scoped(db_session, test_tenant_setup):
    """Test registering external asset mapping and verifying tenant boundaries."""
    tenant = test_tenant_setup
    org = tenant["org"]
    drone = tenant["drone"]

    mapping = telemetry_service.create_asset_mapping(
        db_session,
        organization_id=org.id,
        payload=ExternalAssetMappingCreate(
            source_system="DJI_FLIGHTHUB",
            external_asset_id="FC30-SN-001",
            asset_id=drone.id,
            device_model="DJI FlyCart 30",
        ),
    )
    assert mapping.id is not None
    assert mapping.external_asset_id == "FC30-SN-001"
    assert mapping.asset_id == drone.id

    # Resolve asset within tenant
    resolved = telemetry_service.resolve_asset(
        db_session,
        organization_id=org.id,
        source_system="DJI_FLIGHTHUB",
        external_asset_id="FC30-SN-001",
    )
    assert resolved is not None
    assert resolved.id == drone.id

    # Other tenant cannot resolve
    other_org_id = uuid.uuid4()
    resolved_other = telemetry_service.resolve_asset(
        db_session,
        organization_id=other_org_id,
        source_system="DJI_FLIGHTHUB",
        external_asset_id="FC30-SN-001",
    )
    assert resolved_other is None


def test_dji_webhook_signature_verification():
    """Test HMAC-SHA256 signature verification."""
    secret = "test-webhook-secret-12345"
    body = b'{"event":"flight_record.created","bid":"DJI-EV-001"}'
    valid_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert (
        telemetry_service.verify_webhook_signature(
            body, f"sha256={valid_sig}", secret
        )
        is True
    )
    assert (
        telemetry_service.verify_webhook_signature(
            body, "invalid_signature_hex", secret
        )
        is False
    )
    assert (
        telemetry_service.verify_webhook_signature(body, None, secret) is False
    )


def test_telemetry_flight_ingestion_and_idempotency(
    db_session, test_tenant_setup
):
    """Test ingesting a flight via telemetry, verifying utilization increment and duplicate protection."""
    tenant = test_tenant_setup
    org = tenant["org"]
    drone = tenant["drone"]

    # 1. Map external SN to drone
    ext_sn = f"FC30-EXT-{uuid.uuid4().hex[:6]}"
    telemetry_service.create_asset_mapping(
        db_session,
        organization_id=org.id,
        payload=ExternalAssetMappingCreate(
            source_system="DJI_FLIGHTHUB",
            external_asset_id=ext_sn,
            asset_id=drone.id,
        ),
    )

    event_id = f"EV-DJI-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    event = NormalizedTelemetryEvent(
        source_system="DJI_FLIGHTHUB",
        source_event_id=event_id,
        source_asset_id=ext_sn,
        event_type="flight_record.created",
        event_timestamp=now,
        flight=TelemetryFlightPayload(
            flight_number="DJI-FL-001",
            duration_minutes=45,
            cycles=1,
            origin="Vertiport A",
            destination="Vertiport B",
        ),
    )

    # Ingest Event 1st time
    res1 = telemetry_service.process_normalized_event(
        db_session, organization_id=org.id, event=event
    )
    assert res1.status == TelemetryProcessingStatus.PROCESSED
    assert res1.asset_id == drone.id
    assert res1.flight_id is not None

    # Verify flight recorded in database
    flight = db_session.get(Flight, res1.flight_id)
    assert flight is not None
    assert flight.duration_minutes == 45
    assert flight.source == "TELEMETRY"
    assert flight.source_row_id == event_id

    # Verify utilization
    context = asset_service.get_asset_domain_context(
        db_session, organization_id=org.id, asset_id=drone.id
    )
    assert context.utilization.total_minutes == 45
    assert context.utilization.total_cycles == 1

    # Ingest Event 2nd time (Duplicate Idempotency Test)
    res2 = telemetry_service.process_normalized_event(
        db_session, organization_id=org.id, event=event
    )
    assert res2.status == TelemetryProcessingStatus.DUPLICATE
    assert res2.flight_id == res1.flight_id

    # Verify utilization DID NOT duplicate
    context_after = asset_service.get_asset_domain_context(
        db_session, organization_id=org.id, asset_id=drone.id
    )
    assert context_after.utilization.total_minutes == 45
    assert context_after.utilization.total_cycles == 1


def test_unmatched_asset_quarantine(db_session, test_tenant_setup):
    """Test telemetry for an unmapped/unknown device is quarantined and does not modify operational state."""
    tenant = test_tenant_setup
    org = tenant["org"]

    event = NormalizedTelemetryEvent(
        source_system="DJI_FLIGHTHUB",
        source_event_id=f"EV-UNKNOWN-{uuid.uuid4().hex[:6]}",
        source_asset_id="NON_EXISTENT_DRONE_SN",
        event_type="flight_record.created",
        event_timestamp=datetime.now(UTC),
        flight=TelemetryFlightPayload(
            flight_number="DJI-UNKNOWN",
            duration_minutes=30,
        ),
    )

    res = telemetry_service.process_normalized_event(
        db_session, organization_id=org.id, event=event
    )
    assert res.status == TelemetryProcessingStatus.QUARANTINED
    assert res.flight_id is None

    # Check telemetry log
    log = db_session.execute(
        select(TelemetryEventLog).where(
            TelemetryEventLog.organization_id == org.id,
            TelemetryEventLog.source_event_id == event.source_event_id,
        )
    ).scalar_one()
    assert log.processing_status == TelemetryProcessingStatus.QUARANTINED
    assert "cannot be resolved" in log.rejection_reason


def test_battery_and_hums_sensor_telemetry(db_session, test_tenant_setup):
    """Test ingesting battery health telemetry and HUMS sensor readings."""
    tenant = test_tenant_setup
    org = tenant["org"]
    drone = tenant["drone"]
    battery = tenant["battery"]

    ext_sn = f"FC30-BAT-DRONE-{uuid.uuid4().hex[:6]}"
    telemetry_service.create_asset_mapping(
        db_session,
        organization_id=org.id,
        payload=ExternalAssetMappingCreate(
            source_system="DJI_FLIGHTHUB",
            external_asset_id=ext_sn,
            asset_id=drone.id,
        ),
    )

    event = NormalizedTelemetryEvent(
        source_system="DJI_FLIGHTHUB",
        source_event_id=f"EV-BAT-{uuid.uuid4().hex[:6]}",
        source_asset_id=ext_sn,
        event_type="device.osd.telemetry",
        event_timestamp=datetime.now(UTC),
        battery=TelemetryBatteryPayload(
            serial_number=battery.serial_number,
            cycle_count=15,  # was 10
            voltage_v=51.8,
            health_percent=96,
        ),
        readings=[
            TelemetryReadingItem(
                sensor_code=f"MOT_TEMP_{drone.id.hex[:4]}",
                measurement_type="TEMPERATURE",
                value=42.5,
                unit="CELSIUS",
            ),
            TelemetryReadingItem(
                sensor_code=f"VIB_RMS_{drone.id.hex[:4]}",
                measurement_type="VIBRATION",
                value=2.4,
                unit="MM_S",
            ),
        ],
    )

    res = telemetry_service.process_normalized_event(
        db_session, organization_id=org.id, event=event
    )
    assert res.status == TelemetryProcessingStatus.PROCESSED
    assert res.readings_count == 2

    # Verify battery updated
    db_session.refresh(battery)
    assert battery.cycle_count == 15
    assert battery.health_percent == 96
    assert battery.voltage == 51800  # 51.8V in mV

    # Verify HUMS sensor and readings created
    readings = db_session.execute(
        select(HUMSSensorReading).where(
            HUMSSensorReading.organization_id == org.id,
            HUMSSensorReading.asset_id == drone.id,
        )
    ).scalars().all()
    assert len(readings) == 2
    assert all(r.source == "TELEMETRY" for r in readings)
    assert all(r.data_quality == "VALID" for r in readings)


def test_dji_webhook_api_endpoint(db_session, test_tenant_setup):
    """Test the POST /api/v1/telemetry/dji/webhook HTTP endpoint."""
    tenant = test_tenant_setup
    org = tenant["org"]
    drone = tenant["drone"]
    # M20: the webhook now also checks the target tenant's flight_telemetry entitlement.
    from tests.integration.conftest import grant_features

    grant_features(db_session, org.id, "flight_telemetry")

    ext_sn = f"FC30-API-{uuid.uuid4().hex[:6]}"
    telemetry_service.create_asset_mapping(
        db_session,
        organization_id=org.id,
        payload=ExternalAssetMappingCreate(
            source_system="DJI_FLIGHTHUB",
            external_asset_id=ext_sn,
            asset_id=drone.id,
        ),
    )
    db_session.commit()

    app.dependency_overrides[get_db_session] = lambda: db_session
    try:
        client = TestClient(app)

        dji_body = {
            "bid": f"DJI-WEBHOOK-{uuid.uuid4().hex[:6]}",
            "event": "flight_record.created",
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "data": {
                "device_sn": ext_sn,
                "flight_duration": 1800,  # 30 mins
                "cycles": 1,
                "takeoff_location": "Hub-1",
                "landing_location": "Hub-2",
            },
        }

        import hashlib
        import hmac
        import json as _json
        from types import SimpleNamespace

        from app.api.v1 import telemetry as telemetry_api

        secret = "unit-test-webhook-secret"
        raw = _json.dumps(dji_body).encode()
        sig = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        ct = {"Content-Type": "application/json"}
        org_hdr = {"X-Organization-ID": str(org.id)}
        real_get_settings = telemetry_api.get_settings

        def _with_secret(value):
            telemetry_api.get_settings = lambda: SimpleNamespace(dji_webhook_secret=value)

        try:
            # M20 forensic fix: this endpoint previously accepted UNSIGNED requests
            # (signature was only checked if the header happened to be sent, with a
            # hardcoded fallback secret), letting anyone write telemetry into any
            # tenant. The old assertion here expected 200 for an unsigned request.
            _with_secret(None)  # not configured -> disabled
            r = client.post("/api/v1/telemetry/dji/webhook", content=raw, headers={**ct, **org_hdr, "X-DJI-Signature": sig})
            assert r.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

            _with_secret(secret)
            r = client.post("/api/v1/telemetry/dji/webhook", content=raw, headers={**ct, **org_hdr})
            assert r.status_code == status.HTTP_401_UNAUTHORIZED  # unsigned
            r = client.post("/api/v1/telemetry/dji/webhook", content=raw, headers={**ct, **org_hdr, "X-DJI-Signature": "sha256=deadbeef"})
            assert r.status_code == status.HTTP_401_UNAUTHORIZED  # bad signature
            r = client.post("/api/v1/telemetry/dji/webhook", content=raw, headers={**ct, "X-DJI-Signature": sig})
            assert r.status_code == status.HTTP_400_BAD_REQUEST  # signed, no org

            resp = client.post(
                "/api/v1/telemetry/dji/webhook",
                content=raw,
                headers={**ct, **org_hdr, "X-DJI-Signature": sig},
            )
            assert resp.status_code == status.HTTP_200_OK
            data = resp.json()
            assert data["status"] == "PROCESSED"
            assert data["asset_id"] == str(drone.id)
            assert data["flight_id"] is not None
        finally:
            telemetry_api.get_settings = real_get_settings
    finally:
        app.dependency_overrides.pop(get_db_session, None)
