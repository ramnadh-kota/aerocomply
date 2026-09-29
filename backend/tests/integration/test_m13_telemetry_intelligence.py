"""M13 Phase 3: Telemetry -> HUMS -> M7 Intelligence -> Grounded LISA Integration Tests.

Verifies:
1. End-to-End Lineage:
   External Telemetry (DJI/Generic) -> TelemetryEventLog -> HUMSSensorReading ->
   HUMSFeature/Exceedance -> Finding -> Evidence -> M7 ProactiveSignalRecord -> LISA Explanation.
2. Missing Telemetry Uncertainty:
   Missing telemetry is explicitly communicated as NO_TELEMETRY_RECORDED (never asserted as healthy).
3. Stale Telemetry Early-Warning:
   Old telemetry (> 7 days) triggers TELEMETRY_FRESHNESS early warning signal with Evidence.
4. Tenant Security & Isolation:
   Tenant A cannot view, query, or trigger intelligence/LISA for Tenant B assets.
5. Grounded LISA Investigation:
   LISA retrieves telemetry status, HUMS health, and proactive signals without fabricating facts.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.aircraft import Aircraft
from app.models.asset import Asset
from app.models.evidence import Evidence
from app.models.finding import Finding
from app.models.hums import HUMSExceedance, HUMSSensor, HUMSSensorReading
from app.models.lisa_conversation_context import LisaConversationContext
from app.models.organization import Organization
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.telemetry import ExternalAssetMapping, TelemetryEventLog, TelemetryProcessingStatus
from app.models.user import User, UserRole
from app.schemas.auth import CurrentUser
from app.schemas.telemetry import (
    ExternalAssetMappingCreate,
    NormalizedTelemetryEvent,
    TelemetryFlightPayload,
    TelemetryReadingItem,
)
from app.services import (
    asset_service,
    auth_service,
    drone_service,
    hums_service,
    telemetry_service,
)
from app.services.ai import tools
from app.services.intelligence import proactive_intelligence_service
from app.services.lisa import intent_service, orchestration_service
from app.services.lisa.message_resolution_service import MessageResolution


@pytest.fixture
def horizon_tenant_setup(db_session):
    """Sets up a realistic tenant matching Horizon Air Mobility profile."""
    org_suffix = uuid.uuid4().hex[:6]
    org = Organization(name=f"Horizon Air M13 Phase 3 {org_suffix}")
    db_session.add(org)
    db_session.flush()

    from tests.integration.conftest import grant_features

    grant_features(
        db_session,
        org.id,
        "flight_telemetry",
        "hums",
        "predictive_maintenance",
        "aircraft_fleet_management",
        "lisa_ai_copilot",
        "mro_intelligence",
        "digital_twin",
    )

    admin_user = User(
        organization_id=org.id,
        email=f"camo.manager.{org_suffix}@horizonair.in",
        hashed_password="hashed_pw_test",
        full_name="Rajesh Sharma",
        is_active=True,
    )
    db_session.add(admin_user)
    db_session.flush()

    role_link = UserRole(
        user_id=admin_user.id,
        role_name="ORG_ADMIN",
        organization_id=org.id,
    )
    db_session.add(role_link)
    db_session.flush()

    # Create Drone DR-HZ01
    drone_asset = Asset(
        organization_id=org.id,
        asset_type="DRONE",
        serial_number=f"FC30-DR-HZ01-{org_suffix}",
        registration=f"DR-HZ01-{org_suffix}",
        status="OPERATIONAL",
    )
    db_session.add(drone_asset)
    db_session.flush()

    # Create Aircraft VT-HZA
    aircraft_asset = Asset(
        organization_id=org.id,
        asset_type="AIRCRAFT",
        serial_number=f"MSN-1401-{org_suffix}",
        registration=f"VT-HZA-{org_suffix}",
        status="OPERATIONAL",
    )
    db_session.add(aircraft_asset)
    db_session.flush()

    aircraft = Aircraft(
        organization_id=org.id,
        asset_id=aircraft_asset.id,
        registration=aircraft_asset.registration,
        msn=f"MSN-1401-{org_suffix}",
        aircraft_type="ATR-72-600",
        status="OPERATIONAL",
    )
    db_session.add(aircraft)
    db_session.flush()

    # External asset mapping for DR-HZ01
    mapping = telemetry_service.create_asset_mapping(
        db_session,
        organization_id=org.id,
        payload=ExternalAssetMappingCreate(
            source_system="DJI_FLIGHTHUB",
            external_asset_id=f"FC30-SN-{org_suffix}",
            asset_id=drone_asset.id,
            device_model="FlyCart 30",
        ),
    )
    db_session.commit()

    return {
        "org": org,
        "admin": admin_user,
        "drone": drone_asset,
        "aircraft": aircraft_asset,
        "mapping": mapping,
        "org_suffix": org_suffix,
    }


def test_end_to_end_telemetry_to_lisa_lineage(db_session, horizon_tenant_setup):
    """Scenario A: Telemetry -> Ingestion -> HUMS Sensor Readings ->

    Exceedance -> Finding -> Evidence -> M7 Signal -> Grounded LISA Explanation.
    """
    tenant = horizon_tenant_setup
    org = tenant["org"]
    user = tenant["admin"]
    drone = tenant["drone"]
    mapping = tenant["mapping"]

    current_user = CurrentUser(
        id=user.id,
        organization_id=org.id,
        email=user.email,
        full_name=user.full_name,
        roles=["ORG_ADMIN"],
    )

    # 1. Ingest batch of vibration readings with high RMS (e.g. 9.5 mm/s > 8.0 CRITICAL threshold)
    now = datetime.now(UTC)
    sensor_code = f"MOT_VIB_{uuid.uuid4().hex[:4]}"

    # Ingest 20 readings to satisfy MIN_READINGS_FOR_HEALTH window
    readings = [
        TelemetryReadingItem(
            sensor_code=sensor_code,
            sensor_type="VIBRATION",
            measurement_type="vibration",
            value=9.5,  # Exceeds critical threshold 8.0
            unit="MM_S",
            data_quality="VALID",
        )
        for _ in range(20)
    ]

    event = NormalizedTelemetryEvent(
        source_system="DJI_FLIGHTHUB",
        source_event_id=f"EV-TRACE-{uuid.uuid4().hex[:6]}",
        source_asset_id=mapping.external_asset_id,
        event_type="flight_record.created",
        event_timestamp=now,
        flight=TelemetryFlightPayload(
            flight_number="FC30-MED-101",
            duration_minutes=25,
            cycles=1,
            flown_at=now,
        ),
        readings=readings,
    )

    res = telemetry_service.process_normalized_event(
        db_session, organization_id=org.id, event=event
    )
    assert res.status == TelemetryProcessingStatus.PROCESSED
    assert res.readings_count == 20
    db_session.commit()

    # 2. Verify HUMS Exceedance, Finding, and Evidence were generated
    exceedance = db_session.execute(
        select(HUMSExceedance).where(
            HUMSExceedance.organization_id == org.id,
            HUMSExceedance.asset_id == drone.id,
        )
    ).scalar_one_or_none()
    assert exceedance is not None
    assert exceedance.severity == "CRITICAL"
    assert exceedance.observed_value == 9.5

    finding = db_session.execute(
        select(Finding).where(
            Finding.organization_id == org.id,
            Finding.id == exceedance.finding_id,
        )
    ).scalar_one_or_none()
    assert finding is not None
    assert finding.severity == "CRITICAL"

    evidence = db_session.execute(
        select(Evidence).where(
            Evidence.organization_id == org.id,
            Evidence.finding_id == finding.id,
        )
    ).scalar_one_or_none()
    assert evidence is not None
    assert evidence.evidence_type == "HUMS_TELEMETRY"
    assert "reading_ids" in evidence.provenance

    # 3. Verify M7 Proactive Intelligence Signal
    signals = proactive_intelligence_service.sync_and_get_signals(
        db_session, organization_id=org.id, asset_id=drone.id
    )
    hums_signals = [
        s for s in signals if "HUMS" in s.signal_type or "VIBRATION" in s.signal_type
    ]
    assert len(hums_signals) >= 1
    top_signal = hums_signals[0]
    assert top_signal.severity == "CRITICAL"
    assert len(top_signal.evidence) >= 1
    assert any(ev.source_type == "HUMSExceedance" for ev in top_signal.evidence)

    # 4. Verify LISA Grounded Query
    resolution = MessageResolution(
        context=LisaConversationContext(
            user_id=user.id,
            organization_id=org.id,
            current_aircraft_id=drone.id,
        ),
    )

    lisa_result = orchestration_service.investigate(
        db_session,
        current_user,
        question=f"What is the telemetry and HUMS health status for {drone.registration}?",
        resolution=resolution,
    )
    assert lisa_result is not None
    assert lisa_result.status == "ANSWERED"
    assert "CRITICAL" in lisa_result.headline or "exceedance" in lisa_result.headline
    assert any("Telemetry state: ACTIVE" in f for f in lisa_result.what_i_found)
    assert any("CRITICAL" in f or "exceedance" in f for f in lisa_result.what_i_found)
    assert lisa_result.why_it_matters is not None
    assert lisa_result.next_step is not None
    assert "get_asset_telemetry_status" in lisa_result.tools_invoked


def test_missing_telemetry_uncertainty_semantics(db_session, horizon_tenant_setup):
    """Scenario B: No telemetry recorded for asset ->

    LISA explicitly reports NO_TELEMETRY_RECORDED and uncertainty
    (never states nominal/healthy without proof).
    """
    tenant = horizon_tenant_setup
    org = tenant["org"]
    user = tenant["admin"]
    aircraft = tenant["aircraft"]

    current_user = CurrentUser(
        id=user.id,
        organization_id=org.id,
        email=user.email,
        full_name=user.full_name,
        roles=["ORG_ADMIN"],
    )

    # Asset has 0 telemetry records
    resolution = MessageResolution(
        context=LisaConversationContext(
            user_id=user.id,
            organization_id=org.id,
            current_aircraft_id=aircraft.id,
        ),
    )

    lisa_result = orchestration_service.investigate(
        db_session,
        current_user,
        question=f"Is {aircraft.registration} telemetry healthy?",
        resolution=resolution,
    )
    assert lisa_result is not None
    assert lisa_result.status == "ANSWERED"
    assert "cannot confirm health without verified data" in lisa_result.headline.lower() or "no telemetry recorded" in lisa_result.headline.lower()
    assert any("No telemetry data has been recorded" in f for f in lisa_result.what_i_found)


def test_stale_telemetry_early_warning(db_session, horizon_tenant_setup):
    """Scenario C: Telemetry older than 7 days triggers TELEMETRY_FRESHNESS signal with evidence."""
    tenant = horizon_tenant_setup
    org = tenant["org"]
    user = tenant["admin"]
    drone = tenant["drone"]

    old_time = datetime.now(UTC) - timedelta(days=12)

    # Insert a sensor and an old reading
    sensor = hums_service.create_sensor(
        db_session,
        organization_id=org.id,
        user_id=user.id,
        payload=hums_service.HUMSSensorCreate(
            asset_id=drone.id,
            sensor_code=f"STALE_SENS_{uuid.uuid4().hex[:4]}",
            sensor_type="VIBRATION",
            measurement_type="vibration",
            unit="MM_S",
            source="TELEMETRY",
        ),
    )
    db_session.flush()

    old_reading = HUMSSensorReading(
        organization_id=org.id,
        sensor_id=sensor.id,
        asset_id=drone.id,
        recorded_at=old_time,
        value=2.1,
        unit="MM_S",
        data_quality="VALID",
        source="TELEMETRY",
    )
    db_session.add(old_reading)
    db_session.commit()

    # Sync proactive signals
    signals = proactive_intelligence_service.sync_and_get_signals(
        db_session, organization_id=org.id, asset_id=drone.id
    )
    stale_signals = [s for s in signals if s.signal_type == "TELEMETRY_FRESHNESS"]
    assert len(stale_signals) >= 1
    sig = stale_signals[0]
    assert "Stale" in sig.title
    assert sig.severity == "MEDIUM"
    assert len(sig.evidence) >= 1
    assert sig.evidence[0].source_type == "HUMSSensorReading"


def test_cross_tenant_intelligence_and_lisa_isolation(db_session, horizon_tenant_setup):
    """Scenario D: Tenant B cannot query or view Tenant A telemetry, signals, or LISA context."""
    tenant_a = horizon_tenant_setup
    org_a = tenant_a["org"]
    drone_a = tenant_a["drone"]

    # Create Tenant B
    org_b = Organization(name=f"Competing Airline {uuid.uuid4().hex[:6]}")
    db_session.add(org_b)
    db_session.flush()

    from tests.integration.conftest import grant_features

    grant_features(
        db_session,
        org_b.id,
        "flight_telemetry",
        "hums",
        "predictive_maintenance",
        "aircraft_fleet_management",
        "lisa_ai_copilot",
        "mro_intelligence",
        "digital_twin",
    )

    user_b = User(
        organization_id=org_b.id,
        email=f"admin.{uuid.uuid4().hex[:6]}@competitor.com",
        hashed_password="hashed_pw_test",
        full_name="Competitor Admin",
        is_active=True,
    )
    db_session.add(user_b)
    db_session.flush()

    role_link_b = UserRole(
        user_id=user_b.id,
        role_name="ORG_ADMIN",
        organization_id=org_b.id,
    )
    db_session.add(role_link_b)
    db_session.commit()

    current_user_b = CurrentUser(
        id=user_b.id,
        organization_id=org_b.id,
        email=user_b.email,
        full_name=user_b.full_name,
        roles=["ORG_ADMIN"],
    )

    # User B tries to query telemetry status for Tenant A's drone
    tel_status = tools.execute_tool(
        db_session,
        current_user_b,
        "get_asset_telemetry_status",
        {"asset_id": str(drone_a.id)},
    )
    # Tenant B gets 0 events and NO_TELEMETRY_RECORDED within Tenant B's organization
    assert tel_status["total_recent_events"] == 0
    assert tel_status["telemetry_state"] == "NO_TELEMETRY_RECORDED"

    # User B runs proactive signals for Tenant A's drone -> returns 0 signals
    signals_b = proactive_intelligence_service.sync_and_get_signals(
        db_session, organization_id=org_b.id, asset_id=drone_a.id
    )
    assert len(signals_b) == 0
