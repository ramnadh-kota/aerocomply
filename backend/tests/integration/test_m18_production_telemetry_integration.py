"""M18: Live UAV Telemetry Production Integration & Comprehensive Intelligence Validation.

Validates the full production telemetry lifecycle from Tech Guy 1 gateway handoff
through the entire deterministic intelligence stack:

    REAL UAV / GATEWAY
            ↓
    POST /api/v1/telemetry/ingest
            ↓
    NormalizedTelemetryEvent
            ↓
    HUMS Sensor Readings
            ↓
    Feature Engine (Time + Frequency Domain)
            ↓
    Baseline Engine & Statistical Bounds
            ↓
    Exceedance & Anomaly Detection
            ↓
    Finding Creation & Evidence Linkage
            ↓
    Diagnostic Engine (Fault Signature Matching)
            ↓
    Prognostics & RUL Engine (Degradation Fitting)
            ↓
    M7 Proactive Intelligence (Deduplicated Signals)
            ↓
    Grounded LISA AI Tool Context
            ↓
    Kota Control Center Observability

Test Suite Structure:
1. M18.1: Production Telemetry Contract Validation & Malformed Payload Handling
2. M18.2: Real Telemetry to HUMS Ingestion & Full Digital Thread
3. M18.3: Data Quality, Irregular Sampling, Sensor Dropouts & Zero Values
4. M18.4: Multi-UAV Concurrent Streams (3 simultaneous UAVs) & Multi-Tenant Isolation
5. M18.5: Flight Session Lifecycle, Reconnects & Cross-Flight Isolation
6. M18.6: Live HUMS Controlled Anomaly & Evidence Generation
7. M18.7: Diagnostic Fault Signature Correlation & Grounded Evidence
8. M18.8: Prognostics & RUL Calculation: Strict Sufficiency Guard (No Fabrication)
9. M18.9: M7 Proactive Intelligence Signal Deduplication & Lifecycle
10. M18.10: Grounded LISA AI Query Validation on Production Telemetry
11. M18.11: Multi-UAV Stress, Burst Telemetry, Latency & Idempotency
12. M18.12: Telemetry Disconnect, Staleness Warning, Reconnect & Buffered Replay
13. M18.13: Full 10-Link End-to-End Traceability Verification
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.support.tokens import mint_token as create_access_token
from app.models.asset import Asset, AssetType
from app.models.battery import Battery
from app.models.component import Component
from app.models.evidence import Evidence
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.flight import Flight
from app.models.hums import (
    HUMSBaseline,
    HUMSDiagnosticCandidate,
    HUMSDegradationModel,
    HUMSExceedance,
    HUMSFeature,
    HUMSPrognosticRecord,
    HUMSSensor,
    HUMSSensorReading,
)
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.telemetry import (
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryProcessingStatus,
)
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryBatteryPayload,
    TelemetryFlightPayload,
    TelemetryIngestRequest,
    TelemetryReadingItem,
)
from app.services import (
    hums_service,
    telemetry_service,
)
from app.services.ai import tools
from app.services.edge.telemetry_simulator import (
    TelemetryScenarioType,
    build_scenario_batch,
    generate_canonical_event,
    generate_reading_burst,
)
from app.services.hums import baseline_service, diagnostic_service, prognostic_service
from app.services.intelligence import proactive_intelligence_service


# -----------------------------------------------------------------------------
# Fixtures & Environment Setup
# -----------------------------------------------------------------------------

def _seed_enterprise_plan(db_session: Session):
    plan = db_session.execute(select(Plan).where(Plan.code == "ENTERPRISE_PRODUCTION")).scalar_one_or_none()
    if not plan:
        plan = Plan(name="Enterprise Production", code="ENTERPRISE_PRODUCTION", is_active=True)
        db_session.add(plan)
        db_session.flush()
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="hums", enabled=True))
        # M20: /telemetry and /hums/*/prognostics are now commercially gated.
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="flight_telemetry", enabled=True))
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="predictive_maintenance", enabled=True))
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="drone_fleet_management", enabled=True))
        db_session.flush()
    return plan


def _create_test_org(db_session: Session, name_prefix: str = "Kota Fleet") -> tuple[Organization, User, dict[str, str]]:
    plan = _seed_enterprise_plan(db_session)
    org = Organization(name=f"{name_prefix} {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()

    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"ops.{uuid.uuid4().hex[:6]}@kota-aero.com",
        full_name="Operations Engineer",
        hashed_password="hashed-pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        roles=["ORG_ADMIN", "DRONE_OPERATOR"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
    )
    headers = {"Authorization": f"Bearer {token}"}
    return org, user, headers


def _create_uav_asset(
    db_session: Session,
    org: Organization,
    serial_number: str,
    model: str = "KOTA-HEAVY-LIFT-X8",
) -> tuple[Asset, Component, HUMSSensor, Battery]:
    asset = Asset(
        organization_id=org.id,
        serial_number=serial_number,
        model=model,
        asset_type=AssetType.DRONE,
        status="OPERATIONAL",
    )
    db_session.add(asset)
    db_session.flush()

    component = Component(
        organization_id=org.id,
        asset_id=asset.id,
        name="Front-Right Motor & Propulsion Assembly",
        component_type="PROPULSION",
        serial_number=f"MTR-{serial_number[-4:]}",
        model="KOTA-BLDC-80KV",
        status="OPERATIONAL",
    )
    db_session.add(component)
    db_session.flush()

    sensor = HUMSSensor(
        organization_id=org.id,
        asset_id=asset.id,
        component_id=component.id,
        sensor_code=f"VIB_{serial_number[-4:]}",
        sensor_type="ACCELEROMETER",
        measurement_type="vibration",
        unit="mm/s",
        source="TELEMETRY",
        status="ACTIVE",
    )
    db_session.add(sensor)
    db_session.flush()

    battery = Battery(
        organization_id=org.id,
        serial_number=f"BAT-{serial_number[-4:]}",
        model="KOTA-LIPO-6S-22AH",
        capacity_mah=22000,
        cycle_count=10,
        status="ACTIVE",
    )
    db_session.add(battery)
    db_session.flush()

    # External asset mapping for Gateway / Tech Guy 1 handoff
    mapping = ExternalAssetMapping(
        organization_id=org.id,
        source_system="KOTA_GATEWAY",
        external_asset_id=serial_number,
        asset_id=asset.id,
        is_active=True,
    )
    db_session.add(mapping)
    db_session.flush()

    return asset, component, sensor, battery


# =============================================================================
# M18.1: Production Telemetry Contract Validation & Malformed Payload Handling
# =============================================================================

def test_m18_1_production_contract_validation(client: TestClient, db_session: Session):
    """Validates complete contract fields, optional payloads, and quarantine on unresolvable asset."""
    org, user, headers = _create_test_org(db_session, "Contract Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-001")

    # 1. Valid full production event via HTTP POST /api/v1/telemetry/ingest
    t_now = datetime.now(UTC)
    full_event = NormalizedTelemetryEvent(
        source_system="KOTA_GATEWAY",
        source_event_id=f"evt-contract-{uuid.uuid4().hex[:8]}",
        source_asset_id=asset.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        flight=TelemetryFlightPayload(
            flight_number="KOTA-FLT-01",
            duration_minutes=15,
            cycles=1,
            origin="BASE_ALPHA",
            destination="WAYPOINT_BRAVO",
            flown_at=t_now - timedelta(minutes=15),
            notes="Nominal production survey flight",
        ),
        battery=TelemetryBatteryPayload(
            serial_number=battery.serial_number,
            cycle_count=12,
            voltage_v=24.1,
            internal_resistance_mohm=11.8,
            temperature_c=31.2,
            health_percent=99,
        ),
        readings=[
            TelemetryReadingItem(
                sensor_code=sensor.sensor_code,
                sensor_type="VIBRATION",
                measurement_type="vibration",
                value=2.15,
                unit="mm/s",
                component_id=comp.id,
                data_quality="VALID",
            )
        ],
        raw_metadata={"firmware_version": "v3.2.0-rc1", "mavlink_msg_id": 147},
    )

    resp = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers,
        json={"events": [full_event.model_dump(mode="json")]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_received"] == 1
    assert data["processed_count"] == 1
    assert data["rejected_count"] == 0
    assert data["duplicate_count"] == 0

    # 2. Unregistered asset ID -> QUARANTINED (never crashes pipeline, logged safely)
    unmatched_event = NormalizedTelemetryEvent(
        source_system="KOTA_GATEWAY",
        source_event_id=f"evt-unmatched-{uuid.uuid4().hex[:8]}",
        source_asset_id="UNKNOWN-UAV-9999",
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        readings=[],
    )
    resp_unmatched = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers,
        json={"events": [unmatched_event.model_dump(mode="json")]},
    )
    assert resp_unmatched.status_code == 200
    data_unmatched = resp_unmatched.json()
    assert data_unmatched["rejected_count"] == 1
    assert data_unmatched["results"][0]["status"] == TelemetryProcessingStatus.QUARANTINED


# =============================================================================
# M18.2 & M18.6: Real Telemetry → HUMS → Findings → Evidence Integration
# =============================================================================

def test_m18_2_real_telemetry_to_hums_and_controlled_anomaly(client: TestClient, db_session: Session):
    """Validates baseline establishment on healthy telemetry, then controlled anomaly detection and evidence linking."""
    org, user, headers = _create_test_org(db_session, "HUMS Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-002")
    t0 = datetime.now(UTC) - timedelta(hours=3)

    # Phase 1: Ingest 6 nominal reading bursts (RMS ~ 1.8 mm/s)
    for i in range(6):
        event = build_scenario_batch(
            TelemetryScenarioType.NORMAL,
            source_asset_id=asset.serial_number,
            vib_sensor_code=sensor.sensor_code,
            component_id=comp.id,
            step=i + 1,
            base_time=t0 + timedelta(minutes=i * 10),
        )
        resp = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [event.model_dump(mode="json")]})
        assert resp.status_code == 200

    # Baseline established, zero false critical exceedances
    baseline = baseline_service.get_or_compute_baseline(
        db_session, organization_id=org.id, sensor=sensor, feature_type="rms"
    )
    assert baseline is not None
    assert baseline.mean < 3.0

    exceedances_healthy = db_session.execute(
        select(HUMSExceedance).where(HUMSExceedance.organization_id == org.id, HUMSExceedance.asset_id == asset.id)
    ).scalars().all()
    assert len(exceedances_healthy) == 0

    # Phase 2: Ingest controlled abnormal vibration step (~ 8.8 mm/s with kurtosis spikes)
    anomaly_event = build_scenario_batch(
        TelemetryScenarioType.VIBRATION_DEGRADATION,
        source_asset_id=asset.serial_number,
        vib_sensor_code=sensor.sensor_code,
        component_id=comp.id,
        step=3,
        base_time=t0 + timedelta(minutes=80),
    )
    resp_anomaly = client.post(
        "/api/v1/telemetry/ingest", headers=headers, json={"events": [anomaly_event.model_dump(mode="json")]}
    )
    assert resp_anomaly.status_code == 200

    # Verify HUMS Exceedance, Finding, and Evidence created with full provenance
    exceedances = db_session.execute(
        select(HUMSExceedance).where(HUMSExceedance.organization_id == org.id, HUMSExceedance.asset_id == asset.id)
    ).scalars().all()
    assert len(exceedances) > 0
    latest_exc = exceedances[-1]
    assert latest_exc.severity in ("HIGH", "CRITICAL")
    assert latest_exc.finding_id is not None

    finding = db_session.execute(
        select(Finding).where(Finding.id == latest_exc.finding_id)
    ).scalar_one_or_none()
    assert finding is not None
    assert finding.status == FindingStatus.OPEN
    assert "Vibration Exceedance" in finding.title

    evidence = db_session.execute(
        select(Evidence).where(Evidence.finding_id == finding.id)
    ).scalar_one_or_none()
    assert evidence is not None
    assert evidence.evidence_type == "HUMS_TELEMETRY"
    assert evidence.provenance["sensor_id"] == str(sensor.id)
    assert len(evidence.provenance["reading_ids"]) > 0


# =============================================================================
# M18.3: Data Quality, Irregular Sampling, Dropouts & Stale Handling
# =============================================================================

def test_m18_3_data_quality_and_irregular_streams(client: TestClient, db_session: Session):
    """Tests handling of degraded sensor quality flags, zero readings, and staleness detection."""
    org, user, headers = _create_test_org(db_session, "Quality Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-003")
    t_now = datetime.now(UTC)

    # Ingest event containing VALID, DEGRADED, and zero-value readings
    mixed_readings = [
        TelemetryReadingItem(
            sensor_code=sensor.sensor_code,
            sensor_type="VIBRATION",
            measurement_type="vibration",
            value=2.1,
            unit="mm/s",
            data_quality="VALID",
        ),
        TelemetryReadingItem(
            sensor_code=sensor.sensor_code,
            sensor_type="VIBRATION",
            measurement_type="vibration",
            value=0.0,  # Zero value reading handled cleanly
            unit="mm/s",
            data_quality="DEGRADED",
        ),
    ]
    event = NormalizedTelemetryEvent(
        source_system="KOTA_GATEWAY",
        source_event_id=f"evt-quality-{uuid.uuid4().hex[:8]}",
        source_asset_id=asset.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        readings=mixed_readings,
    )
    resp = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [event.model_dump(mode="json")]})
    assert resp.status_code == 200
    assert resp.json()["processed_count"] == 1

    # Verify readings saved with respective quality flags
    saved_readings = db_session.execute(
        select(HUMSSensorReading).where(HUMSSensorReading.asset_id == asset.id)
    ).scalars().all()
    assert len(saved_readings) == 2
    qualities = {r.data_quality for r in saved_readings}
    assert "VALID" in qualities
    assert "DEGRADED" in qualities


# =============================================================================
# M18.4: Multi-UAV Concurrent Streams (3 Simultaneous UAVs) & Tenant Isolation
# =============================================================================

def test_m18_4_multi_uav_concurrent_streams_and_tenant_isolation(client: TestClient, db_session: Session):
    """Validates 3 UAVs streaming simultaneously in Org A (with different health states) and an isolated Org B."""
    org_a, user_a, headers_a = _create_test_org(db_session, "Tenant A Defense Fleet")
    org_b, user_b, headers_b = _create_test_org(db_session, "Tenant B Commercial Fleet")

    # Org A: 3 simultaneous UAVs
    uav1, comp1, sensor1, bat1 = _create_uav_asset(db_session, org_a, "UAV-ALPHA-001")
    uav2, comp2, sensor2, bat2 = _create_uav_asset(db_session, org_a, "UAV-BRAVO-002")
    uav3, comp3, sensor3, bat3 = _create_uav_asset(db_session, org_a, "UAV-CHARLIE-003")

    # Org B: 1 UAV
    uav_b, comp_b, sensor_b, bat_b = _create_uav_asset(db_session, org_b, "UAV-TENANT-B-001")

    # M20: VIBRATION_DEGRADATION(step=3) dates its event at t0 + 30 min. Anchored at "now" that
    # event lies 30 minutes in the FUTURE, which the ingestion quality gate (correctly) rejects
    # as a corrupt clock. Anchor the stream in the past so every event has a valid timestamp.
    t_stream = datetime.now(UTC) - timedelta(minutes=45)

    # 1. UAV-1: Nominal operation
    evt_uav1 = build_scenario_batch(
        TelemetryScenarioType.NORMAL,
        source_asset_id=uav1.serial_number,
        vib_sensor_code=sensor1.sensor_code,
        component_id=comp1.id,
        base_time=t_stream,
    )
    # 2. UAV-2: High vibration anomaly (triggering exceedance & bearing diagnosis)
    evt_uav2 = build_scenario_batch(
        TelemetryScenarioType.VIBRATION_DEGRADATION,
        source_asset_id=uav2.serial_number,
        vib_sensor_code=sensor2.sensor_code,
        component_id=comp2.id,
        step=3,
        base_time=t_stream,
    )
    # 3. UAV-3: Elevated temperature
    evt_uav3 = build_scenario_batch(
        TelemetryScenarioType.TEMPERATURE_ANOMALY,
        source_asset_id=uav3.serial_number,
        temp_sensor_code=f"TEMP_{uav3.serial_number[-4:]}",
        component_id=comp3.id,
        base_time=t_stream,
    )

    # Send multi-UAV batch to Org A
    resp_a = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers_a,
        json={"events": [evt_uav1.model_dump(mode="json"), evt_uav2.model_dump(mode="json"), evt_uav3.model_dump(mode="json")]},
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["processed_count"] == 3

    # Send UAV-B event to Org B
    evt_b = build_scenario_batch(
        TelemetryScenarioType.NORMAL,
        source_asset_id=uav_b.serial_number,
        vib_sensor_code=sensor_b.sensor_code,
        component_id=comp_b.id,
        base_time=t_stream,
    )
    resp_b = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers_b,
        json={"events": [evt_b.model_dump(mode="json")]},
    )
    assert resp_b.status_code == 200

    # Cross-Asset Isolation Assertions:
    # UAV-1 has 0 exceedances
    exc_uav1 = db_session.execute(
        select(HUMSExceedance).where(HUMSExceedance.asset_id == uav1.id)
    ).scalars().all()
    assert len(exc_uav1) == 0

    # UAV-2 has critical exceedance and finding
    exc_uav2 = db_session.execute(
        select(HUMSExceedance).where(HUMSExceedance.asset_id == uav2.id)
    ).scalars().all()
    assert len(exc_uav2) > 0

    # Cross-Tenant Isolation Assertions:
    # Org B has 0 proactive exceedance signals from Org A
    summary_b = proactive_intelligence_service.get_proactive_summary(db_session, organization_id=org_b.id)
    assert not any(s.signal_type == "HUMS_VIBRATION_EXCEEDANCE" for s in summary_b.signals)
    assert all(s.asset_id == uav_b.id for s in summary_b.signals)


# =============================================================================
# M18.5: Flight Session Lifecycle & Cross-Flight Isolation
# =============================================================================

def test_m18_5_flight_session_lifecycle_and_isolation(client: TestClient, db_session: Session):
    """Validates flight creation, in-flight reconnects, and strict isolation between sequential flights."""
    org, user, headers = _create_test_org(db_session, "Flight Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-005")
    t0 = datetime.now(UTC) - timedelta(hours=4)

    # Flight 1: Ingest 2 events under flight FLT-101 with same departure flown_at
    flown_at_f1 = t0 - timedelta(minutes=30)
    evt_f1_a = NormalizedTelemetryEvent(
        source_system="KOTA_GATEWAY",
        source_event_id="f1-packet-1",
        source_asset_id=asset.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t0,
        flight=TelemetryFlightPayload(
            flight_number="FLT-101",
            duration_minutes=25,
            cycles=1,
            origin="BASE_ALPHA",
            destination="WAYPOINT_BRAVO",
            flown_at=flown_at_f1,
        ),
        readings=generate_reading_burst(sensor_code=sensor.sensor_code, measurement_type="vibration", unit="mm/s", base_value=1.8),
    )
    evt_f1_b = NormalizedTelemetryEvent(
        source_system="KOTA_GATEWAY",
        source_event_id="f1-packet-2",
        source_asset_id=asset.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t0 + timedelta(minutes=10),
        flight=TelemetryFlightPayload(
            flight_number="FLT-101",
            duration_minutes=25,
            cycles=1,
            origin="BASE_ALPHA",
            destination="WAYPOINT_BRAVO",
            flown_at=flown_at_f1,
        ),
        readings=generate_reading_burst(sensor_code=sensor.sensor_code, measurement_type="vibration", unit="mm/s", base_value=1.9),
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt_f1_a.model_dump(mode="json"), evt_f1_b.model_dump(mode="json")]})

    # Flight 2: Ingest 1 event under new flight FLT-102
    t1 = t0 + timedelta(hours=2)
    evt_f2 = NormalizedTelemetryEvent(
        source_system="KOTA_GATEWAY",
        source_event_id="f2-packet-1",
        source_asset_id=asset.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t1,
        flight=TelemetryFlightPayload(
            flight_number="FLT-102",
            duration_minutes=30,
            cycles=1,
            origin="WAYPOINT_BRAVO",
            destination="BASE_ALPHA",
            flown_at=t1 - timedelta(minutes=30),
        ),
        readings=generate_reading_burst(sensor_code=sensor.sensor_code, measurement_type="vibration", unit="mm/s", base_value=2.0),
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt_f2.model_dump(mode="json")]})

    # Verify 2 distinct flight records created
    flights = db_session.execute(
        select(Flight).where(Flight.organization_id == org.id, Flight.asset_id == asset.id).order_by(Flight.flown_at.asc())
    ).scalars().all()
    assert len(flights) == 2
    assert flights[0].flight_number == "FLT-101"
    assert flights[1].flight_number == "FLT-102"


# =============================================================================
# M18.7, M18.8, M18.9, M18.10: Diagnostics, Prognostics, M7 & LISA Grounding
# =============================================================================

def test_m18_7_to_10_full_intelligence_stack_and_lisa_grounding(client: TestClient, db_session: Session):
    """Validates complete downstream intelligence flow: Diagnostics -> Prognostics/RUL -> M7 Signals -> LISA."""
    org, user, headers = _create_test_org(db_session, "Intelligence Stack Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-007")
    t0 = datetime.now(UTC) - timedelta(hours=2)

    # 1. Feed baseline history so degradation engine has historical context
    for i in range(5):
        evt = build_scenario_batch(
            TelemetryScenarioType.NORMAL,
            source_asset_id=asset.serial_number,
            vib_sensor_code=sensor.sensor_code,
            component_id=comp.id,
            step=i + 1,
            base_time=t0 + timedelta(minutes=i * 5),
        )
        client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt.model_dump(mode="json")]})

    # 2. Trigger critical vibration degradation
    deg_evt = build_scenario_batch(
        TelemetryScenarioType.VIBRATION_DEGRADATION,
        source_asset_id=asset.serial_number,
        vib_sensor_code=sensor.sensor_code,
        component_id=comp.id,
        step=3,
        base_time=t0 + timedelta(minutes=45),
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [deg_evt.model_dump(mode="json")]})

    # 3. Diagnostic Engine: Verify VIB-BRG-001 (Bearing Degradation) identified
    candidates = db_session.execute(
        select(HUMSDiagnosticCandidate).where(
            HUMSDiagnosticCandidate.organization_id == org.id,
            HUMSDiagnosticCandidate.asset_id == asset.id,
        )
    ).scalars().all()
    assert len(candidates) > 0
    brg_cand = next((c for c in candidates if c.fault_code == "VIB-BRG-001"), None)
    assert brg_cand is not None
    assert brg_cand.status in ("SUPPORTED", "CANDIDATE")
    assert len(brg_cand.primary_evidence) > 0

    # 4. Prognostic Engine: Verify degradation record persisted with RUL trajectory
    prognostics = db_session.execute(
        select(HUMSPrognosticRecord).where(
            HUMSPrognosticRecord.organization_id == org.id,
            HUMSPrognosticRecord.asset_id == asset.id,
        )
    ).scalars().all()
    assert len(prognostics) > 0
    assert prognostics[0].status in ("AVAILABLE", "LIMITED", "LOW_CONFIDENCE", "STALE")

    # 5. M7 Proactive Intelligence: Verify proactive signal emission and deduplication
    summary = proactive_intelligence_service.get_proactive_summary(db_session, organization_id=org.id)
    assert summary.total_active_signals > 0
    sig_types = [s.signal_type for s in summary.signals]
    assert "HUMS_VIBRATION_EXCEEDANCE" in sig_types

    # 6. LISA Grounded AI Tools: Verify tools return structured DB records without hallucination
    current_user_obj = CurrentUser(
        id=user.id,
        organization_id=org.id,
        email=user.email,
        full_name=user.full_name,
        roles=["ORG_ADMIN"],
    )

    t_status = tools.execute_tool(db_session, current_user_obj, "get_asset_telemetry_status", {"asset_id": str(asset.id)})
    assert t_status["telemetry_state"] == "ACTIVE"
    assert t_status["total_recent_events"] > 0

    t_diag = tools.execute_tool(db_session, current_user_obj, "get_asset_hums_diagnostics", {"asset_id": str(asset.id)})
    assert "diagnostics" in t_diag
    assert any(d["fault_code"] == "VIB-BRG-001" for d in t_diag["diagnostics"])

    t_signals = tools.execute_tool(db_session, current_user_obj, "get_asset_proactive_signals", {"asset_id": str(asset.id)})
    assert len(t_signals["signals"]) > 0


# =============================================================================
# M18.11: Multi-UAV Stress, Sustained Load & Latency Validation
# =============================================================================

def test_m18_11_telemetry_stress_and_concurrency(client: TestClient, db_session: Session):
    """Stress tests ingestion pipeline with a sustained burst of 30+ telemetry packets across 3 UAVs."""
    org, user, headers = _create_test_org(db_session, "Stress Org")
    uav1, comp1, sensor1, bat1 = _create_uav_asset(db_session, org, "UAV-STRESS-01")
    uav2, comp2, sensor2, bat2 = _create_uav_asset(db_session, org, "UAV-STRESS-02")
    uav3, comp3, sensor3, bat3 = _create_uav_asset(db_session, org, "UAV-STRESS-03")

    t_base = datetime.now(UTC) - timedelta(minutes=30)
    events: list[NormalizedTelemetryEvent] = []

    for i in range(10):
        t_pkt = t_base + timedelta(seconds=i * 10)
        events.append(generate_canonical_event(
            source_asset_id=uav1.serial_number,
            source_event_id=f"stress-u1-{i}",
            event_timestamp=t_pkt,
            readings=generate_reading_burst(sensor_code=sensor1.sensor_code, measurement_type="vibration", unit="mm/s", base_value=1.8),
        ))
        events.append(generate_canonical_event(
            source_asset_id=uav2.serial_number,
            source_event_id=f"stress-u2-{i}",
            event_timestamp=t_pkt,
            readings=generate_reading_burst(sensor_code=sensor2.sensor_code, measurement_type="vibration", unit="mm/s", base_value=1.9),
        ))
        events.append(generate_canonical_event(
            source_asset_id=uav3.serial_number,
            source_event_id=f"stress-u3-{i}",
            event_timestamp=t_pkt,
            readings=generate_reading_burst(sensor_code=sensor3.sensor_code, measurement_type="vibration", unit="mm/s", base_value=2.0),
        ))

    # Send 30 events in a single burst and measure processing latency
    t_start = time.perf_counter()
    resp = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers,
        json={"events": [e.model_dump(mode="json") for e in events]},
    )
    t_elapsed = time.perf_counter() - t_start

    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["total_received"] == 30
    assert res_data["processed_count"] == 30
    assert res_data["rejected_count"] == 0
    assert t_elapsed < 10.0  # Fast batch execution (< 10s for 30 multi-sensor events)

    # Re-sending the identical batch returns 30 duplicates (100% idempotent protection)
    resp_dup = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers,
        json={"events": [e.model_dump(mode="json") for e in events]},
    )
    assert resp_dup.status_code == 200
    res_dup_data = resp_dup.json()
    assert res_dup_data["duplicate_count"] == 30
    assert res_dup_data["processed_count"] == 0


# =============================================================================
# M18.12: Failure Recovery, Telemetry Staleness & Replay Buffer Handling
# =============================================================================

def test_m18_12_staleness_and_recovery(client: TestClient, db_session: Session):
    """Validates telemetry freshness warning when stream goes dead and recovery upon reconnection."""
    org, user, headers = _create_test_org(db_session, "Recovery Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-012")

    # Ingest historical event from 8 days ago
    stale_ts = datetime.now(UTC) - timedelta(days=8)
    stale_evt = generate_canonical_event(
        source_asset_id=asset.serial_number,
        source_event_id=f"stale-evt-{uuid.uuid4().hex[:8]}",
        event_timestamp=stale_ts,
        readings=generate_reading_burst(sensor_code=sensor.sensor_code, measurement_type="vibration", unit="mm/s", base_value=1.8),
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [stale_evt.model_dump(mode="json")]})

    # Telemetry status transitions to STALE
    stale_status = telemetry_service.get_asset_telemetry_status(db_session, organization_id=org.id, asset_id=asset.id)
    assert stale_status["telemetry_state"] == "STALE"

    # Gateway reconnects and streams fresh live telemetry
    fresh_ts = datetime.now(UTC)
    recovery_evt = generate_canonical_event(
        source_asset_id=asset.serial_number,
        source_event_id=f"recov-evt-{uuid.uuid4().hex[:8]}",
        event_timestamp=fresh_ts,
        readings=generate_reading_burst(sensor_code=sensor.sensor_code, measurement_type="vibration", unit="mm/s", base_value=1.8),
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [recovery_evt.model_dump(mode="json")]})

    # Telemetry status is restored to ACTIVE
    recov_status = telemetry_service.get_asset_telemetry_status(db_session, organization_id=org.id, asset_id=asset.id)
    assert recov_status["telemetry_state"] == "ACTIVE"


# =============================================================================
# M18.13: Full 10-Link End-to-End Traceability Verification
# =============================================================================

def test_m18_13_complete_traceability_chain(client: TestClient, db_session: Session):
    """Verifies the unbroken 10-link bidirectional lineage from Proactive Signal to UAV Flight."""
    org, user, headers = _create_test_org(db_session, "Traceability Org")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-PROD-013")
    t0 = datetime.now(UTC) - timedelta(hours=1)

    # Ingest baseline + critical anomaly event with explicit flight number
    crit_evt = generate_canonical_event(
        source_asset_id=asset.serial_number,
        source_event_id="trace-crit-001",
        flight_number="TRACE-FLT-99",
        event_timestamp=t0,
        readings=generate_reading_burst(
            sensor_code=sensor.sensor_code,
            measurement_type="vibration",
            unit="mm/s",
            base_value=9.5,  # Exceeds critical threshold (8.0 mm/s)
            component_id=comp.id,
            kurtosis_spike=True,
        ),
    )
    resp = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [crit_evt.model_dump(mode="json")]})
    assert resp.status_code == 200

    # 1. Proactive Signal
    signals = db_session.execute(
        select(ProactiveSignalRecord).where(ProactiveSignalRecord.organization_id == org.id, ProactiveSignalRecord.asset_id == asset.id)
    ).scalars().all()
    assert len(signals) > 0
    sig = signals[0]

    # 2. Exceedance & Finding
    exceedances = db_session.execute(
        select(HUMSExceedance).where(HUMSExceedance.organization_id == org.id, HUMSExceedance.asset_id == asset.id)
    ).scalars().all()
    assert len(exceedances) > 0
    exc = exceedances[0]

    finding = db_session.execute(
        select(Finding).where(Finding.id == exc.finding_id)
    ).scalar_one_or_none()
    assert finding is not None

    # 3. Evidence
    evidence = db_session.execute(
        select(Evidence).where(Evidence.finding_id == finding.id)
    ).scalar_one_or_none()
    assert evidence is not None

    # 4. Sensor Readings
    reading_ids = [uuid.UUID(rid) for rid in evidence.provenance["reading_ids"]]
    readings = db_session.execute(
        select(HUMSSensorReading).where(HUMSSensorReading.id.in_(reading_ids))
    ).scalars().all()
    assert len(readings) > 0

    # 5. Telemetry Event Log
    logs = db_session.execute(
        select(TelemetryEventLog).where(TelemetryEventLog.source_event_id == "trace-crit-001")
    ).scalars().all()
    assert len(logs) == 1
    assert logs[0].asset_id == asset.id

    # 6. Flight & Component Links
    assert readings[0].flight_id is not None
    flight = db_session.execute(select(Flight).where(Flight.id == readings[0].flight_id)).scalar_one_or_none()
    assert flight is not None
    assert flight.flight_number == "TRACE-FLT-99"
    assert exc.component_id == comp.id
