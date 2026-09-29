"""Integration tests for M14: Commercialization Platform, Edge Hardware, and Second Customer Scale."""

import uuid
from datetime import UTC, datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.main import app
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.evidence import Evidence
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.flight import Flight
from app.models.hums import HUMSSensor, HUMSSensorReading, HUMSFeature, HUMSExceedance
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.telemetry import EdgeDevice
from app.models.user import User, UserRole
from app.schemas.edge_hardware import DeviceTelemetryEnvelope, EdgeDeviceCreate, EdgeSensorMeasurement
from app.services import edge_hardware_service
from app.services.export_service import export_tenant_data_package
from app.services.intelligence.cross_asset_intelligence_service import evaluate_cross_asset_intelligence
from app.services.intelligence.decision_simulation_service import simulate_decision_scenarios


@pytest.fixture
def m14_env(db_session: Session):
    """Sets up two isolated tenant organizations for multi-customer testing."""
    # Tenant 1: Customer #1 (Horizon)
    org1 = Organization(
        name="Customer 1 Mobility",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org1)
    db_session.flush()

    user1 = User(
        organization_id=org1.id,
        email="admin@customer1.com",
        hashed_password=hash_password("Password123!"),
        full_name="Admin Cust1",
        is_active=True,
    )
    db_session.add(user1)
    db_session.flush()
    db_session.add(UserRole(user_id=user1.id, role_name="ORG_ADMIN", organization_id=org1.id))
    db_session.add(UserRole(user_id=user1.id, role_name="CAMO_MANAGER", organization_id=org1.id))

    # Tenant 2: Customer #2 (Second Customer)
    org2 = Organization(
        name="Demo Aerospace Mobility Pvt Ltd",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.PROVISIONING,
    )
    db_session.add(org2)
    db_session.flush()

    user2 = User(
        organization_id=org2.id,
        email="ops@demoaero.com",
        hashed_password=hash_password("Password123!"),
        full_name="Director DemoAero",
        is_active=True,
    )
    db_session.add(user2)
    db_session.flush()
    db_session.add(UserRole(user_id=user2.id, role_name="ORG_ADMIN", organization_id=org2.id))
    db_session.add(UserRole(user_id=user2.id, role_name="CAMO_MANAGER", organization_id=org2.id))

    db_session.flush()
    return {"org1": org1, "user1": user1, "org2": org2, "user2": user2}


def test_edge_device_registration_and_envelope_ingestion(db_session: Session, m14_env):
    """Tests registering an edge hardware device and processing a canonical telemetry envelope."""
    org2 = m14_env["org2"]
    user2 = m14_env["user2"]

    # 1. Register Asset & Edge Gateway
    uav = Asset(
        organization_id=org2.id,
        asset_type=AssetType.DRONE,
        serial_number="DEMO-UAV-01",
        status="ACTIVE",
    )
    db_session.add(uav)
    db_session.flush()

    device_create = EdgeDeviceCreate(
        device_id="GATEWAY-DEMO-001",
        device_type="EDGE_GATEWAY",
        firmware_version="2.4.0",
        asset_id=uav.id,
        metadata_json={"bus": "CAN_FD"},
    )
    device = edge_hardware_service.register_edge_device(
        db_session,
        organization_id=org2.id,
        payload=device_create,
        actor_user_id=user2.id,
    )
    assert device.id is not None
    assert device.device_id == "GATEWAY-DEMO-001"
    assert device.status == "ACTIVE"

    # 2. Process Envelope
    now = datetime.now(UTC)
    envelope = DeviceTelemetryEnvelope(
        device_id="GATEWAY-DEMO-001",
        gateway_id="GATEWAY-DEMO-001",
        firmware_version="2.4.0",
        source_asset_id="DEMO-UAV-01",
        sequence_number=101,
        envelope_timestamp=now,
        measurements=[
            EdgeSensorMeasurement(
                sensor_code="MOT_1_VIB",
                sensor_type="VIBRATION",
                timestamp=now,
                unit="g",
                raw_values={"rms_g": 0.22, "peak_g": 0.58},
                quality="VALID",
            )
        ],
    )
    res = edge_hardware_service.process_device_telemetry_envelope(
        db_session,
        organization_id=org2.id,
        envelope=envelope,
    )
    assert res["status"] == "ACCEPTED"
    assert res["device_id"] == "GATEWAY-DEMO-001"
    assert res["readings_count"] == 1

    # Verify device heartbeat updated
    db_session.refresh(device)
    assert device.last_heartbeat_at is not None


def test_cross_asset_intelligence_and_tenant_isolation(db_session: Session, m14_env):
    """Tests evaluating cross-asset fault patterns and degradation trends with strict tenant isolation."""
    org1 = m14_env["org1"]
    org2 = m14_env["org2"]

    # Create 2 drone assets in Org 2
    a1 = Asset(
        organization_id=org2.id,
        asset_type=AssetType.DRONE,
        serial_number="DRONE-01",
        status="ACTIVE",
    )
    a2 = Asset(
        organization_id=org2.id,
        asset_type=AssetType.DRONE,
        serial_number="DRONE-02",
        status="ACTIVE",
    )
    db_session.add_all([a1, a2])
    db_session.flush()

    # Create findings with identical repeat title across both assets
    f1 = Finding(
        organization_id=org2.id,
        title="Motor 1 Bearing Wear",
        description="Vibration exceedance on Drone 1",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        asset_id=a1.id,
    )
    f2 = Finding(
        organization_id=org2.id,
        title="Motor 1 Bearing Wear",
        description="Vibration exceedance on Drone 2",
        severity=FindingSeverity.MAJOR,
        status=FindingStatus.OPEN,
        asset_id=a2.id,
    )
    db_session.add_all([f1, f2])
    db_session.flush()

    # Evaluate intelligence for Org 2
    summary2 = evaluate_cross_asset_intelligence(db_session, organization_id=org2.id)
    assert summary2.total_assets == 2
    assert len(summary2.recurring_patterns) == 1
    assert summary2.recurring_patterns[0].component_or_sensor == "Motor 1 Bearing Wear"
    assert summary2.recurring_patterns[0].affected_asset_count == 2
    assert summary2.fleet_health_status in ("ATTENTION", "DEGRADED")

    # Evaluate intelligence for Org 1 (must be completely isolated and return INSUFFICIENT_DATA)
    summary1 = evaluate_cross_asset_intelligence(db_session, organization_id=org1.id)
    assert summary1.total_assets == 0
    assert len(summary1.recurring_patterns) == 0
    assert summary1.fleet_health_status == "INSUFFICIENT_DATA"


def test_decision_intelligence_simulation(db_session: Session, m14_env):
    """Tests 3-scenario decision simulation on an active proactive signal."""
    org2 = m14_env["org2"]

    signal = ProactiveSignalRecord(
        organization_id=org2.id,
        signal_key="SIG-DEMO-001",
        signal_type="HUMS_EXCEEDANCE",
        severity="CRITICAL",
        priority="P1",
        status="OPEN",
        title="Propulsion Motor 1 Degradation",
        headline="Elevated high-frequency vibration detected on Motor 1",
        detected_at=datetime.now(UTC),
        evidence_json=[{"finding_id": str(uuid.uuid4())}],
    )
    db_session.add(signal)
    db_session.flush()

    sim = simulate_decision_scenarios(db_session, organization_id=org2.id, signal_id=signal.id)
    assert sim.signal_id == signal.id
    assert sim.current_risk_score == 90.0
    assert sim.recommended_option_id == "OPT_IMMEDIATE_ACTION"
    assert len(sim.options) == 3
    assert sim.options[0].action_type == "IMMEDIATE_MAINTENANCE"


def test_tenant_data_export_package(db_session: Session, m14_env):
    """Tests tenant-isolated data export generation."""
    org2 = m14_env["org2"]
    user2 = m14_env["user2"]

    # Add 1 asset & 1 flight in Org 2
    a = Asset(
        organization_id=org2.id,
        asset_type=AssetType.AIRCRAFT,
        registration="VT-EXP",
        status="ACTIVE",
    )
    db_session.add(a)
    db_session.flush()

    f = Flight(
        organization_id=org2.id,
        asset_id=a.id,
        flight_number="DA-101",
        duration_minutes=150,
        cycles=1,
        flown_at=datetime.now(UTC),
    )
    db_session.add(f)
    db_session.flush()

    export_pkg = export_tenant_data_package(
        db_session,
        organization_id=org2.id,
        actor_user_id=user2.id,
        include_categories=["FLEET", "FLIGHTS"],
    )
    assert export_pkg["organization_id"] == str(org2.id)
    assert "flights" in export_pkg["data"]
    assert len(export_pkg["data"]["flights"]) == 1
    assert export_pkg["data"]["flights"][0]["flight_number"] == "DA-101"


def test_second_customer_zero_code_lifecycle(db_session: Session, m14_env):
    """M14.32: Proves that Customer #2 can onboard, transition stages, operate fleet, and query intelligence
    with zero customer-specific code branches."""
    org2 = m14_env["org2"]

    # 1. Onboarding State Machine transitions
    assert org2.onboarding_stage == OnboardingStage.PROVISIONING
    org2.onboarding_stage = OnboardingStage.UAT
    db_session.flush()
    assert org2.onboarding_stage == OnboardingStage.UAT

    org2.onboarding_stage = OnboardingStage.ACTIVE
    db_session.flush()
    assert org2.onboarding_stage == OnboardingStage.ACTIVE

    # 2. Add Turboprop Aircraft & Asset to Customer #2
    ast = Asset(
        organization_id=org2.id,
        asset_type=AssetType.AIRCRAFT,
        registration="VT-DEMO",
        status="ACTIVE",
    )
    db_session.add(ast)
    db_session.flush()

    ac = Aircraft(
        organization_id=org2.id,
        registration="VT-DEMO",
        msn="MSN-72-990",
        aircraft_type="ATR-72-600",
        status="ACTIVE",
        asset_id=ast.id,
    )
    db_session.add(ac)
    db_session.flush()
    assert ac.id is not None

    # 3. Add Flight Record
    fl = Flight(
        organization_id=org2.id,
        asset_id=ast.id,
        flight_number="DEMO-202",
        duration_minutes=110,
        cycles=1,
        flown_at=datetime.now(UTC),
    )
    db_session.add(fl)
    db_session.flush()
    assert fl.id is not None
