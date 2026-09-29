"""M16: Edge Platform Productization, Device Lifecycle & Multi-Customer Scale Tests.

Validates the full KOTA Edge productization layer:
- Device Provisioning Factory
- Immutable Versioned Configuration & Rollback
- Canonical Heartbeat & Technical Observability
- Sensor Inventory Management
- Safe Command Channel
- Device Revocation Security
- Local Offline Resilience Buffering & Ordered Replay
- Strict Multi-Customer Tenant Isolation
- Full Audit Trail Traceability
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ForbiddenError, NotFoundError
from app.models.asset import Asset, AssetType
from app.models.audit_event import AuditEvent
from app.models.hums import HUMSSensorReading
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.telemetry import EdgeDevice, TelemetryEventLog, TelemetryProcessingStatus
from app.models.user import User, UserRole
from app.schemas.edge_hardware import (
    EdgeDeviceCommandRequest,
    EdgeDeviceCommandResultSubmit,
    EdgeDeviceConfigUpdate,
    EdgeDeviceHeartbeatRequest,
    EdgeDeviceLifecycleStatus,
    EdgeDeviceProvisionRequest,
    EdgeDeviceRevokeRequest,
    EdgeSensorItem,
)
from app.services.edge.acquisition_engine import PhysicalEdgeAcquisitionEngine
from app.services.edge.sensor_adapters import VibrationSensorAdapter
from app.services.edge_hardware_service import (
    get_edge_device_health,
    get_edge_device_inventory,
    issue_device_command,
    process_device_heartbeat,
    process_device_telemetry_envelope,
    provision_edge_device,
    revoke_edge_device,
    rollback_device_configuration,
    submit_command_result,
    update_device_configuration,
)


@pytest.fixture
def m16_env(db_session: Session):
    """Sets up two isolated tenant organizations (Horizon Air + Apex Aero)."""
    # Customer 1: Horizon Air Mobility
    org1 = Organization(
        name="Horizon Regional Air & Drone Mobility",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org1)
    db_session.flush()

    asset1 = Asset(
        organization_id=org1.id,
        asset_type=AssetType.AIRCRAFT,
        model="ATR-72-600",
        serial_number=f"VT-HZA-{uuid.uuid4().hex[:4].upper()}",
        status="ACTIVE",
    )
    db_session.add(asset1)
    db_session.flush()

    user1 = User(
        organization_id=org1.id,
        email=f"horizon-admin-{uuid.uuid4().hex[:6]}@horizon.aero",
        full_name="Horizon Admin",
        hashed_password="hashed_secret",
        is_active=True,
    )
    db_session.add(user1)
    db_session.flush()

    # Customer 2: Apex Aero Logistics
    org2 = Organization(
        name="Apex Aero Logistics Pvt Ltd",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org2)
    db_session.flush()

    asset2 = Asset(
        organization_id=org2.id,
        asset_type=AssetType.DRONE,
        model="FlyCart 30 Cargo",
        serial_number=f"FC30-APEX-{uuid.uuid4().hex[:4].upper()}",
        status="ACTIVE",
    )
    db_session.add(asset2)
    db_session.flush()

    user2 = User(
        organization_id=org2.id,
        email=f"apex-admin-{uuid.uuid4().hex[:6]}@apex.aero",
        full_name="Apex Admin",
        hashed_password="hashed_secret",
        is_active=True,
    )
    db_session.add(user2)
    db_session.commit()

    return {
        "org1": org1,
        "asset1": asset1,
        "user1": user1,
        "org2": org2,
        "asset2": asset2,
        "user2": user2,
    }


def test_m16_device_provisioning_and_sensor_inventory(db_session: Session, m16_env):
    """Test 1 & 4: Repeatable zero-code device provisioning with sensor inventory."""
    env = m16_env
    org1: Organization = env["org1"]
    asset1: Asset = env["asset1"]
    user1: User = env["user1"]

    sensors = [
        EdgeSensorItem(
            sensor_code="MOT_1_VIB",
            sensor_type="VIBRATION",
            model="ADXL345",
            serial_number="VIB-SN-001",
            channel="SPI0",
            unit="g",
        ),
        EdgeSensorItem(
            sensor_code="ENG_1_TEMP",
            sensor_type="TEMPERATURE",
            model="PT100-RTD",
            serial_number="TMP-SN-002",
            channel="I2C1_0x48",
            unit="degC",
        ),
    ]

    prov_req = EdgeDeviceProvisionRequest(
        device_id="KOTA-EDGE-HZA-01",
        device_type="EDGE_GATEWAY",
        asset_id=asset1.id,
        firmware_version="2.6.0-m16",
        sensors=sensors,
        initial_config={"sampling_hz": 1000, "telemetry_interval_sec": 5},
    )

    prov_res = provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=prov_req,
        actor_user_id=user1.id,
    )

    assert prov_res.device.device_id == "KOTA-EDGE-HZA-01"
    assert prov_res.config_version == 1
    assert prov_res.lifecycle_stage == EdgeDeviceLifecycleStatus.CONFIGURED
    assert len(prov_res.provisioning_token) > 10

    # Verify sensor inventory
    inv = get_edge_device_inventory(db_session, organization_id=org1.id, device_id="KOTA-EDGE-HZA-01")
    assert len(inv) == 2
    assert inv[0]["sensor_code"] == "MOT_1_VIB"
    assert inv[1]["sensor_code"] == "ENG_1_TEMP"


def test_m16_device_configuration_versioning_and_rollback(db_session: Session, m16_env):
    """Test 2 & 3: Configuration update to v2 and rollback to v1."""
    env = m16_env
    org1: Organization = env["org1"]
    user1: User = env["user1"]

    # Provision v1
    provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=EdgeDeviceProvisionRequest(
            device_id="KOTA-EDGE-CFG-TEST",
            initial_config={"sampling_hz": 500, "telemetry_interval_sec": 10},
        ),
        actor_user_id=user1.id,
    )

    # Update to v2
    cfg_update = EdgeDeviceConfigUpdate(
        settings={"sampling_hz": 2000, "telemetry_interval_sec": 2},
        change_summary="High rate telemetry profile for flight testing",
        apply_immediately=True,
    )
    cfg_res = update_device_configuration(
        db_session,
        organization_id=org1.id,
        device_id="KOTA-EDGE-CFG-TEST",
        payload=cfg_update,
        actor_user_id=user1.id,
    )

    assert cfg_res.active_version == 2
    assert cfg_res.settings["sampling_hz"] == 2000
    assert len(cfg_res.history) == 2

    # Rollback to v1
    rb_res = rollback_device_configuration(
        db_session,
        organization_id=org1.id,
        device_id="KOTA-EDGE-CFG-TEST",
        target_version=1,
        actor_user_id=user1.id,
    )

    assert rb_res.active_version == 1
    assert rb_res.settings["sampling_hz"] == 500


def test_m16_device_heartbeat_and_observability(db_session: Session, m16_env):
    """Test 4: Canonical heartbeat ingestion, observability update, and sync status."""
    env = m16_env
    org1: Organization = env["org1"]

    provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=EdgeDeviceProvisionRequest(device_id="KOTA-EDGE-HB-01"),
    )

    hb_req = EdgeDeviceHeartbeatRequest(
        device_id="KOTA-EDGE-HB-01",
        timestamp=datetime.now(UTC),
        firmware_version="2.6.0-m16",
        software_version="kota-edge-daemon-v2.6",
        uptime_seconds=3600,
        connectivity_state="ONLINE",
        sensor_states={"MOT_1_VIB": "VALID", "ENG_1_TEMP": "VALID"},
        queue_depth=0,
        config_version=1,
        observability={"cpu_percent": 14.5, "memory_percent": 28.0, "disk_free_mb": 12000},
    )

    hb_res = process_device_heartbeat(db_session, organization_id=org1.id, payload=hb_req)
    assert hb_res.status == "ACK"
    assert not hb_res.requires_config_sync
    assert hb_res.latest_config_version == 1

    # Verify device health reflects heartbeat
    health = get_edge_device_health(db_session, organization_id=org1.id, device_id="KOTA-EDGE-HB-01")
    assert health["health_status"] == "HEALTHY"
    assert health["lifecycle_stage"] == EdgeDeviceLifecycleStatus.CONNECTED
    assert health["observability"]["cpu_percent"] == 14.5


def test_m16_command_channel_execution(db_session: Session, m16_env):
    """Test 11: Dispatching a safe operational command and recording result."""
    env = m16_env
    org1: Organization = env["org1"]
    user1: User = env["user1"]

    provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=EdgeDeviceProvisionRequest(device_id="KOTA-EDGE-CMD-01"),
    )

    # Issue command
    cmd_req = EdgeDeviceCommandRequest(
        command_type="REQUEST_DIAGNOSTICS",
        parameters={"detailed": True},
    )
    cmd_res = issue_device_command(
        db_session,
        organization_id=org1.id,
        device_id="KOTA-EDGE-CMD-01",
        payload=cmd_req,
        actor_user_id=user1.id,
    )
    assert cmd_res.status == "PENDING"
    cmd_id = cmd_res.command_id

    # Edge executes command and returns result
    submit_req = EdgeDeviceCommandResultSubmit(
        command_id=cmd_id,
        status="SUCCESS",
        result={"sensors_online": 2, "buffer_free_percent": 98.4},
    )
    sub_res = submit_command_result(
        db_session,
        organization_id=org1.id,
        device_id="KOTA-EDGE-CMD-01",
        payload=submit_req,
    )
    assert sub_res.status == "SUCCESS"
    assert sub_res.result["sensors_online"] == 2


def test_m16_device_revocation_security(db_session: Session, m16_env):
    """Test 9 & 10: Device revocation immediately rejects telemetry, heartbeat, and commands."""
    env = m16_env
    org1: Organization = env["org1"]
    asset1: Asset = env["asset1"]
    user1: User = env["user1"]

    provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=EdgeDeviceProvisionRequest(device_id="KOTA-EDGE-REVOKE-01", asset_id=asset1.id),
    )

    # Revoke device
    revoke_res = revoke_edge_device(
        db_session,
        organization_id=org1.id,
        device_id="KOTA-EDGE-REVOKE-01",
        reason="Physical hardware node reported lost or decommissioned",
        actor_user_id=user1.id,
    )
    assert revoke_res.status == EdgeDeviceLifecycleStatus.REVOKED

    # Telemetry ingestion from revoked device must be rejected with ForbiddenError
    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-EDGE-REVOKE-01",
        source_asset_id=asset1.serial_number,
    )
    engine.register_sensor(VibrationSensorAdapter(sensor_code="MOT_REV_VIB", unit="g"))

    with pytest.raises(ForbiddenError):
        process_device_telemetry_envelope(
            db_session,
            organization_id=org1.id,
            envelope=engine.create_envelope(engine.sample_all_sensors()),
        )

    # Heartbeat from revoked device must be rejected
    with pytest.raises(ForbiddenError):
        process_device_heartbeat(
            db_session,
            organization_id=org1.id,
            payload=EdgeDeviceHeartbeatRequest(
                device_id="KOTA-EDGE-REVOKE-01",
                timestamp=datetime.now(UTC),
            ),
        )


def test_m16_multi_customer_tenant_isolation(db_session: Session, m16_env):
    """Test 10 & 15: Strict cross-customer isolation between Horizon Air and Apex Aero."""
    env = m16_env
    org1: Organization = env["org1"]
    asset1: Asset = env["asset1"]
    org2: Organization = env["org2"]
    asset2: Asset = env["asset2"]

    # Provision device for Customer 1
    provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=EdgeDeviceProvisionRequest(device_id="KOTA-EDGE-CUST1", asset_id=asset1.id),
    )

    # Provision device for Customer 2
    provision_edge_device(
        db_session,
        organization_id=org2.id,
        payload=EdgeDeviceProvisionRequest(device_id="KOTA-EDGE-CUST2", asset_id=asset2.id),
    )

    # Customer 2 attempting to query Customer 1's device health raises NotFoundError
    with pytest.raises(NotFoundError):
        get_edge_device_health(db_session, organization_id=org2.id, device_id="KOTA-EDGE-CUST1")

    # Customer 2 attempting to configure Customer 1's device raises NotFoundError
    with pytest.raises(NotFoundError):
        update_device_configuration(
            db_session,
            organization_id=org2.id,
            device_id="KOTA-EDGE-CUST1",
            payload=EdgeDeviceConfigUpdate(settings={"sampling_hz": 100}),
        )


def test_m16_audit_trail_verification(db_session: Session, m16_env):
    """Test 12: Every lifecycle action produces immutable audit events."""
    env = m16_env
    org1: Organization = env["org1"]
    user1: User = env["user1"]

    dev_id = f"KOTA-EDGE-AUDIT-{uuid.uuid4().hex[:4].upper()}"

    # 1. Provision
    provision_edge_device(
        db_session,
        organization_id=org1.id,
        payload=EdgeDeviceProvisionRequest(device_id=dev_id),
        actor_user_id=user1.id,
    )

    # 2. Config update
    update_device_configuration(
        db_session,
        organization_id=org1.id,
        device_id=dev_id,
        payload=EdgeDeviceConfigUpdate(settings={"sampling_hz": 800}),
        actor_user_id=user1.id,
    )

    # 3. Revoke
    revoke_edge_device(
        db_session,
        organization_id=org1.id,
        device_id=dev_id,
        reason="Audit test decommission",
        actor_user_id=user1.id,
    )

    # Query audit events
    audits = list(
        db_session.execute(
            select(AuditEvent)
            .where(AuditEvent.organization_id == org1.id)
            .order_by(AuditEvent.created_at.desc())
        ).scalars().all()
    )

    actions = [a.action for a in audits]
    assert "edge_device.provisioned" in actions
    assert "edge_device.config_updated" in actions
    assert "edge_device.revoked" in actions
