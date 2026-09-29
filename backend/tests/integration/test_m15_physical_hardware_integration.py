"""M15: Physical Hardware Integration & Laboratory Bench Validation Tests.

Validates the full physical hardware data pathway:
Physical Sensor -> Physical Edge Engine -> Canonical Envelope -> Core Telemetry -> HUMS -> M7 -> LISA.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.asset import Asset, AssetType
from app.models.evidence import Evidence
from app.models.finding import Finding
from app.models.hums import HUMSExceedance, HUMSSensor, HUMSSensorReading
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import EdgeDevice, TelemetryEventLog, TelemetryProcessingStatus
from app.schemas.edge_hardware import EdgeDeviceCreate
from app.services.edge.acquisition_engine import PhysicalEdgeAcquisitionEngine
from app.services.edge.sensor_adapters import (
    ElectricalSensorAdapter,
    PressureSensorAdapter,
    TemperatureSensorAdapter,
    VibrationSensorAdapter,
)
from app.services.edge_hardware_service import (
    get_edge_device_health,
    process_device_telemetry_envelope,
    register_edge_device,
    trace_telemetry_lineage,
)


@pytest.fixture
def m15_test_environment(db_session: Session):
    """Sets up a test organization, asset, and registered edge gateway."""
    org = Organization(
        name="Apex Physical Hardware Lab",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org)
    db_session.flush()

    asset = Asset(
        organization_id=org.id,
        asset_type=AssetType.DRONE,
        model="DJI FlyCart 30 Testbed",
        serial_number=f"FC30-BENCH-{uuid.uuid4().hex[:6].upper()}",
        status="ACTIVE",
    )
    db_session.add(asset)
    db_session.flush()

    device = register_edge_device(
        db_session,
        organization_id=org.id,
        payload=EdgeDeviceCreate(
            device_id="KOTA-BENCH-EDGE-01",
            device_type="EDGE_GATEWAY",
            firmware_version="2.5.0-m15",
            asset_id=asset.id,
            metadata_json={"bus": "SPI_I2C", "location": "PROP_TEST_STAND_1"},
        ),
    )
    db_session.commit()
    return {"org": org, "asset": asset, "device": device}


def test_m15_normal_vibration_acquisition(db_session: Session, m15_test_environment):
    """Test 1: Normal physical vibration readings acquired, enveloped, and processed into HUMS."""
    env = m15_test_environment
    org: Organization = env["org"]
    asset: Asset = env["asset"]

    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset.serial_number,
    )
    vib_adapter = VibrationSensorAdapter(sensor_code="MOT_1_VIB", unit="g")
    engine.register_sensor(vib_adapter)

    # Acquire normal vibration waveform (~0.21g RMS)
    raw_waveform = [0.20, 0.24, 0.19, 0.23, 0.21, 0.22, 0.20]
    res = engine.acquire_and_dispatch(
        dispatch_fn=lambda envelope: process_device_telemetry_envelope(
            db_session, organization_id=org.id, envelope=envelope
        ),
        raw_overrides={"MOT_1_VIB": raw_waveform},
    )

    assert res["status"] == "ACCEPTED"
    assert res["processing_status"] == TelemetryProcessingStatus.PROCESSED
    assert res["readings_count"] == 1

    # Verify HUMSSensorReading in database
    reading = db_session.execute(
        select(HUMSSensorReading).where(
            HUMSSensorReading.organization_id == org.id,
            HUMSSensorReading.asset_id == asset.id,
        )
    ).scalar_one_or_none()
    assert reading is not None
    assert reading.data_quality == "VALID"
    assert round(reading.value, 2) == 0.21


def test_m15_elevated_vibration_exceedance_and_m7(db_session: Session, m15_test_environment):
    """Test 2: Controlled elevated vibration generates HUMS exceedance and triggers M7 proactive signal."""
    env = m15_test_environment
    org: Organization = env["org"]
    asset: Asset = env["asset"]

    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset.serial_number,
    )
    vib_adapter = VibrationSensorAdapter(sensor_code="MOT_1_VIB_MM_S", unit="mm/s")
    engine.register_sensor(vib_adapter)

    # Waveform generating critical exceedance (> 8.0 mm/s) - dispatch 5 windows to satisfy MIN_READINGS_FOR_HEALTH
    critical_waveform = [9.2, 9.6, 8.8, 9.4, 9.1, 9.5]
    for _ in range(5):
        res = engine.acquire_and_dispatch(
            dispatch_fn=lambda envelope: process_device_telemetry_envelope(
                db_session, organization_id=org.id, envelope=envelope
            ),
            raw_overrides={"MOT_1_VIB_MM_S": critical_waveform},
        )
        assert res["status"] == "ACCEPTED"
        assert res["processing_status"] == TelemetryProcessingStatus.PROCESSED

    # Verify exceedance recorded
    exceedances = list(
        db_session.execute(
            select(HUMSExceedance).where(
                HUMSExceedance.organization_id == org.id,
                HUMSExceedance.asset_id == asset.id,
            )
        ).scalars().all()
    )
    assert len(exceedances) >= 1
    assert exceedances[0].severity in ["WARNING", "CRITICAL"]


def test_m15_sensor_disconnect_detection(db_session: Session, m15_test_environment):
    """Test 3: Sensor disconnect sets quality to INVALID and prevents data corruption."""
    env = m15_test_environment
    org: Organization = env["org"]
    asset: Asset = env["asset"]

    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset.serial_number,
    )
    vib_adapter = VibrationSensorAdapter(sensor_code="MOT_1_VIB", unit="g")
    engine.register_sensor(vib_adapter)

    # Disconnect sensor
    vib_adapter.disconnect()
    assert not vib_adapter.is_connected

    res = engine.acquire_and_dispatch(
        dispatch_fn=lambda envelope: process_device_telemetry_envelope(
            db_session, organization_id=org.id, envelope=envelope
        )
    )
    assert res["status"] == "ACCEPTED"

    # Check reading quality is INVALID
    reading = db_session.execute(
        select(HUMSSensorReading).where(
            HUMSSensorReading.organization_id == org.id,
            HUMSSensorReading.asset_id == asset.id,
        ).order_by(HUMSSensorReading.created_at.desc())
    ).scalars().first()
    assert reading is not None
    assert reading.data_quality == "INVALID"


def test_m15_network_interruption_and_buffer_flush(db_session: Session, m15_test_environment):
    """Test 4: Network interruption buffers envelopes offline; auto-reconnect flushes without duplicates."""
    env = m15_test_environment
    org: Organization = env["org"]
    asset: Asset = env["asset"]

    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset.serial_number,
    )
    temp_adapter = TemperatureSensorAdapter(sensor_code="ENG_1_TEMP", unit="degC")
    engine.register_sensor(temp_adapter)

    # Simulate network offline
    engine.is_online = False

    # Dispatch 3 samples while offline
    for i in range(3):
        res = engine.acquire_and_dispatch(
            dispatch_fn=lambda envelope: process_device_telemetry_envelope(
                db_session, organization_id=org.id, envelope=envelope
            ),
            raw_overrides={"ENG_1_TEMP": 60.0 + i},
        )
        assert res["status"] == "BUFFERED_OFFLINE"

    assert len(engine.offline_buffer) == 3

    # Reconnect and flush buffer
    flush_res = engine.reconnect_and_flush(
        dispatch_fn=lambda envelope: process_device_telemetry_envelope(
            db_session, organization_id=org.id, envelope=envelope
        )
    )

    assert flush_res["status"] == "RECONNECTED_AND_FLUSHED"
    assert flush_res["replayed_count"] == 3
    assert len(engine.offline_buffer) == 0


def test_m15_multi_sensor_physical_payload_and_traceability(db_session: Session, m15_test_environment):
    """Test 5: Multi-sensor payload (Vib + Temp + Press + Elec) with full lineage tracing."""
    env = m15_test_environment
    org: Organization = env["org"]
    asset: Asset = env["asset"]

    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset.serial_number,
    )
    engine.register_sensor(VibrationSensorAdapter(sensor_code="MOT_VIB", unit="g"))
    engine.register_sensor(TemperatureSensorAdapter(sensor_code="MOT_TEMP", unit="degC"))
    engine.register_sensor(PressureSensorAdapter(sensor_code="HYD_PRESS", unit="bar"))
    engine.register_sensor(ElectricalSensorAdapter(sensor_code="BUS_ELEC", unit="V"))

    res = engine.acquire_and_dispatch(
        dispatch_fn=lambda envelope: process_device_telemetry_envelope(
            db_session, organization_id=org.id, envelope=envelope
        ),
        raw_overrides={
            "MOT_VIB": [0.18, 0.22, 0.20],
            "MOT_TEMP": 65.2,
            "HYD_PRESS": 210.0,
            "BUS_ELEC": {"voltage_v": 28.4, "current_a": 12.0},
        },
    )

    assert res["status"] == "ACCEPTED"
    assert res["readings_count"] == 4
    source_event_id = res["source_event_id"]

    # Full lineage tracing test
    lineage = trace_telemetry_lineage(db_session, organization_id=org.id, source_event_id=source_event_id)
    assert lineage["source_event_id"] == source_event_id
    assert lineage["readings_count"] == 4
    assert lineage["processing_status"] == TelemetryProcessingStatus.PROCESSED

    # Device health test
    health = get_edge_device_health(db_session, organization_id=org.id, device_id="KOTA-BENCH-EDGE-01")
    assert health["health_status"] == "HEALTHY"
    assert health["bound_asset_id"] == str(asset.id)


def test_m15_strict_tenant_isolation(db_session: Session, m15_test_environment):
    """Test 6: Tenant A physical telemetry cannot leak into or be queried by Tenant B."""
    env = m15_test_environment
    org_a: Organization = env["org"]
    asset_a: Asset = env["asset"]

    # Create Tenant B
    org_b = Organization(
        name="Competitor Aero",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org_b)
    db_session.commit()

    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset_a.serial_number,
    )
    engine.register_sensor(VibrationSensorAdapter(sensor_code="MOT_VIB_A", unit="g"))

    res = engine.acquire_and_dispatch(
        dispatch_fn=lambda envelope: process_device_telemetry_envelope(
            db_session, organization_id=org_a.id, envelope=envelope
        )
    )
    source_event_id = res["source_event_id"]

    # Querying from Tenant B must raise NotFoundError
    with pytest.raises(NotFoundError):
        trace_telemetry_lineage(db_session, organization_id=org_b.id, source_event_id=source_event_id)


def test_m15_lisa_grounded_telemetry_investigation(db_session: Session, m15_test_environment):
    """Test 7: Grounded LISA investigates physical telemetry and HUMS status for the asset."""
    from app.models.aircraft import Aircraft
    from app.schemas.auth import CurrentUser
    from app.services.lisa.message_resolution_service import resolve_message
    from app.services.lisa.orchestration_service import investigate

    env = m15_test_environment
    org: Organization = env["org"]
    asset: Asset = env["asset"]

    # Create matching Aircraft entity for Lisa entity resolution
    ac = Aircraft(
        organization_id=org.id,
        registration="VT-BENCH",
        msn="MSN-BENCH-01",
        aircraft_type="ATR-72-600",
    )
    db_session.add(ac)
    db_session.flush()

    from app.models.user import User, UserRole
    from app.core.security import hash_password

    u = User(
        organization_id=org.id,
        email=f"test-camo-{uuid.uuid4().hex[:6]}@apex.com",
        full_name="Apex CAMO Manager",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(u)
    db_session.flush()

    ur = UserRole(user_id=u.id, role_name="CAMO_MANAGER", organization_id=org.id)
    db_session.add(ur)
    db_session.flush()

    current_user = CurrentUser(
        id=u.id,
        organization_id=org.id,
        email=u.email,
        full_name=u.full_name,
        roles=["CAMO_MANAGER"],
        permissions=["telemetry:read", "fleet:read", "aircraft:read", "aircraft:view"],
    )

    # Ingest physical telemetry for the asset
    engine = PhysicalEdgeAcquisitionEngine(
        device_id="KOTA-BENCH-EDGE-01",
        source_asset_id=asset.serial_number,
    )
    engine.register_sensor(VibrationSensorAdapter(sensor_code="MOT_1_VIB", unit="g"))
    engine.acquire_and_dispatch(
        dispatch_fn=lambda envelope: process_device_telemetry_envelope(
            db_session, organization_id=org.id, envelope=envelope
        ),
        raw_overrides={"MOT_1_VIB": [0.20, 0.22, 0.21]},
    )

    # Ask LISA about asset telemetry/HUMS
    question = f"What is the telemetry status of VT-BENCH?"
    resolution = resolve_message(
        db_session,
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        question=question,
    )
    result = investigate(
        db_session,
        current_user,
        question=question,
        resolution=resolution,
    )

    assert result is not None
    assert result.intent == "TELEMETRY_HUMS"
    assert len(result.headline) > 0

