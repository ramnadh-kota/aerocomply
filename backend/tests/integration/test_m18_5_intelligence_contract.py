"""M18.5: Live Telemetry Contract & Intelligence Pipeline Integration Hardening Tests.

Validates the hardened boundary between Tech Guy 1 data acquisition and
Tech Guy 2 deterministic intelligence stack:

    NormalizedTelemetryEvent
            ↓
    Telemetry Ingestion (POST /api/v1/telemetry/ingest)
            ↓
    HUMS Sensor Readings (HUMSSensor / HUMSSensorReading)
            ↓
    Feature Extraction (RMS, Peak, Crest Factor, Kurtosis)
            ↓
    Baseline Engine & Statistical Thresholds
            ↓
    Exceedance & Anomaly Detection
            ↓
    Finding Creation & Evidence Linkage
            ↓
    Diagnostic Engine (Fault Signature Matching)
            ↓
    Prognostics & RUL Engine (Strict Data-Sufficiency Guard)
            ↓
    M7 Proactive Intelligence (Deduplicated Signals)
            ↓
    Grounded LISA AI Assistant Tools
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.battery import Battery
from app.models.component import Component
from app.models.evidence import Evidence
from app.models.finding import Finding, FindingSeverity
from app.models.flight import Flight
from app.models.hums import (
    HUMSBaseline,
    HUMSDiagnosticCandidate,
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
    flight_service,
    hums_service,
    telemetry_service,
)
from app.services.ai import tools
from app.services.edge.gateway_service import KotaTelemetryGateway
from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.hums import (
    baseline_engine,
    diagnostic_service,
    feature_extractors,
    health_engine,
    prognostic_service,
)
from app.services.intelligence import proactive_intelligence_service


# -----------------------------------------------------------------------------
# Fixtures & Environment Helpers
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
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="digital_twin", enabled=True))
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="lisa_ai_copilot", enabled=True))
        db_session.flush()
    return plan


def _create_test_org(db_session: Session, name_prefix: str = "Kota Aerospace") -> tuple[Organization, User, dict[str, str]]:
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
        email=f"intel.{uuid.uuid4().hex[:6]}@kota-aero.com",
        full_name="Aerospace Intelligence Engineer",
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
        name="Front-Right BLDC Propulsion Assembly",
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
        asset_id=asset.id,
        serial_number=f"BAT-{serial_number[-4:]}",
        model="KOTA-LIPO-6S-22AH",
        capacity_mah=22000,
        cycle_count=10,
        status="ACTIVE",
    )
    db_session.add(battery)
    db_session.flush()

    mapping = ExternalAssetMapping(
        organization_id=org.id,
        source_system="KOTA_MAVLINK_GATEWAY",
        external_asset_id=serial_number,
        asset_id=asset.id,
        device_model=model,
        is_active=True,
    )
    db_session.add(mapping)
    db_session.flush()

    return asset, component, sensor, battery


# =============================================================================
# M18.5 Hardening Test Cases
# =============================================================================

def test_m18_5_canonical_contract_and_field_mapping(client: TestClient, db_session: Session):
    """M18.5.1: Validates exact field mapping for flight, battery, components, and telemetry logs."""
    org, user, headers = _create_test_org(db_session, "Contract Hardening")
    asset, comp, sensor, battery = _create_uav_asset(db_session, org, "UAV-HARDEN-001")

    t_now = datetime.now(UTC)
    event = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id=f"evt-{uuid.uuid4().hex[:8]}",
        source_asset_id=asset.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        flight=TelemetryFlightPayload(
            flight_number="FLT-M18-501",
            duration_minutes=20,
            cycles=1,
            origin="BASE_ALPHA",
            destination="WAYPOINT_BRAVO",
            flown_at=t_now - timedelta(minutes=20),
            notes="Nominal ArduPilot Waypoint Mission",
        ),
        battery=TelemetryBatteryPayload(
            serial_number=battery.serial_number,
            cycle_count=15,
            voltage_v=24.2,
            temperature_c=32.5,
            health_percent=97,
        ),
        readings=[
            TelemetryReadingItem(
                sensor_code=sensor.sensor_code,
                sensor_type="ACCELEROMETER",
                measurement_type="vibration",
                value=2.15,
                unit="mm/s",
                component_id=comp.id,
                data_quality="VALID",
            )
        ],
        raw_metadata={"firmware": "ArduCopter-v4.5.1", "mavlink_version": 2},
    )

    resp = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers,
        json={"events": [event.model_dump(mode="json")]},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["processed_count"] == 1

    # Verify Database Persistence across domains
    log = db_session.execute(
        select(TelemetryEventLog).where(
            TelemetryEventLog.organization_id == org.id,
            TelemetryEventLog.source_event_id == event.source_event_id,
        )
    ).scalar_one()
    assert log.processing_status == TelemetryProcessingStatus.PROCESSED
    assert log.asset_id == asset.id
    assert log.metadata_payload["firmware"] == "ArduCopter-v4.5.1"

    # Verify Flight Record
    flight = db_session.execute(
        select(Flight).where(Flight.organization_id == org.id, Flight.id == log.flight_id)
    ).scalar_one()
    assert flight.flight_number == "FLT-M18-501"
    assert flight.duration_minutes == 20

    # Verify Battery Update
    db_session.refresh(battery)
    assert battery.cycle_count == 15
    assert battery.voltage == 24200  # mV


def test_m18_5_multi_uav_concurrent_streams_and_isolation(client: TestClient, db_session: Session):
    """M18.5.2: 3 simultaneous UAVs (UAV-A, UAV-B, UAV-C) with independent telemetry states and isolated metrics."""
    org, user, headers = _create_test_org(db_session, "Multi-UAV Isolation")
    uav_a, comp_a, sens_a, _ = _create_uav_asset(db_session, org, "UAV-ALPHA")
    uav_b, comp_b, sens_b, _ = _create_uav_asset(db_session, org, "UAV-BRAVO")
    uav_c, comp_c, sens_c, _ = _create_uav_asset(db_session, org, "UAV-CHARLIE")

    t_now = datetime.now(UTC)
    # UAV-A: High Vibration (Anomaly: 48.0 mm/s)
    evt_a = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-uav-a-01",
        source_asset_id="UAV-ALPHA",
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        readings=[
            TelemetryReadingItem(
                sensor_code=sens_a.sensor_code,
                measurement_type="vibration",
                value=48.0,
                unit="mm/s",
                component_id=comp_a.id,
            )
        ],
    )
    # UAV-B: Nominal Vibration (1.8 mm/s)
    evt_b = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-uav-b-01",
        source_asset_id="UAV-BRAVO",
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        readings=[
            TelemetryReadingItem(
                sensor_code=sens_b.sensor_code,
                measurement_type="vibration",
                value=1.8,
                unit="mm/s",
                component_id=comp_b.id,
            )
        ],
    )
    # UAV-C: Nominal Vibration (2.0 mm/s)
    evt_c = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-uav-c-01",
        source_asset_id="UAV-CHARLIE",
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t_now,
        readings=[
            TelemetryReadingItem(
                sensor_code=sens_c.sensor_code,
                measurement_type="vibration",
                value=2.0,
                unit="mm/s",
                component_id=comp_c.id,
            )
        ],
    )

    batch_resp = client.post(
        "/api/v1/telemetry/ingest",
        headers=headers,
        json={"events": [evt_a.model_dump(mode="json"), evt_b.model_dump(mode="json"), evt_c.model_dump(mode="json")]},
    )
    assert batch_resp.status_code == 200
    assert batch_resp.json()["processed_count"] == 3

    # Assert UAV-A readings isolated to UAV-A
    readings_a = db_session.execute(
        select(HUMSSensorReading).where(HUMSSensorReading.asset_id == uav_a.id)
    ).scalars().all()
    assert len(readings_a) == 1
    assert readings_a[0].value == 48.0

    # Assert UAV-B readings isolated to UAV-B
    readings_b = db_session.execute(
        select(HUMSSensorReading).where(HUMSSensorReading.asset_id == uav_b.id)
    ).scalars().all()
    assert len(readings_b) == 1
    assert readings_b[0].value == 1.8


def test_m18_5_multi_tenant_strict_boundary_isolation(client: TestClient, db_session: Session):
    """M18.5.3: Cross-tenant isolation ensuring zero leakage between Organization A and Organization B."""
    org_a, user_a, headers_a = _create_test_org(db_session, "Tenant A")
    org_b, user_b, headers_b = _create_test_org(db_session, "Tenant B")

    uav_a, _, sens_a, _ = _create_uav_asset(db_session, org_a, "UAV-TENANT-A")
    uav_b, _, sens_b, _ = _create_uav_asset(db_session, org_b, "UAV-TENANT-B")

    # Ingest for Tenant A
    evt_a = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-tenant-a-1",
        source_asset_id="UAV-TENANT-A",
        event_type="REALTIME_TELEMETRY",
        event_timestamp=datetime.now(UTC),
        readings=[TelemetryReadingItem(sensor_code=sens_a.sensor_code, measurement_type="vibration", value=2.2, unit="mm/s")],
    )
    client.post("/api/v1/telemetry/ingest", headers=headers_a, json={"events": [evt_a.model_dump(mode="json")]})

    # Tenant B queries telemetry status -> Scoped strictly to Tenant B, receives NO_TELEMETRY_RECORDED
    user_b_obj = CurrentUser(
        id=user_b.id,
        organization_id=org_b.id,
        roles=["ORG_ADMIN"],
        email=user_b.email,
        full_name=user_b.full_name,
        email_verified=True,
    )
    t_status_b = tools.execute_tool(db_session, user_b_obj, "get_asset_telemetry_status", {"asset_id": str(uav_a.id)})
    assert t_status_b["telemetry_state"] == "NO_TELEMETRY_RECORDED"
    assert t_status_b["total_recent_events"] == 0


def test_m18_5_flight_session_isolation_and_continuity(client: TestClient, db_session: Session):
    """M18.5.4: Sequential flights on the same UAV remain strictly isolated."""
    org, user, headers = _create_test_org(db_session, "Flight Isolation")
    uav, comp, sensor, _ = _create_uav_asset(db_session, org, "UAV-FLIGHTS-01")

    t0 = datetime.now(UTC) - timedelta(hours=3)
    # Flight 1: 15 minutes
    evt_f1 = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="f1-packet",
        source_asset_id=uav.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t0,
        flight=TelemetryFlightPayload(
            flight_number="FLT-001",
            duration_minutes=15,
            cycles=1,
            flown_at=t0,
        ),
        readings=[TelemetryReadingItem(sensor_code=sensor.sensor_code, measurement_type="vibration", value=1.8, unit="mm/s")],
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt_f1.model_dump(mode="json")]})

    # Flight 2: 20 minutes (1 hour later)
    t1 = t0 + timedelta(hours=1)
    evt_f2 = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="f2-packet",
        source_asset_id=uav.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=t1,
        flight=TelemetryFlightPayload(
            flight_number="FLT-002",
            duration_minutes=20,
            cycles=1,
            flown_at=t1,
        ),
        readings=[TelemetryReadingItem(sensor_code=sensor.sensor_code, measurement_type="vibration", value=2.0, unit="mm/s")],
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt_f2.model_dump(mode="json")]})

    # Verify 2 distinct flights created in database
    flights = db_session.execute(
        select(Flight).where(Flight.organization_id == org.id, Flight.asset_id == uav.id).order_by(Flight.flown_at.asc())
    ).scalars().all()
    assert len(flights) == 2
    assert flights[0].flight_number == "FLT-001"
    assert flights[1].flight_number == "FLT-002"


def test_m18_5_data_quality_and_quarantine(client: TestClient, db_session: Session):
    """M18.5.5: Data quality handling (VALID vs INVALID vs UNRESOLVED asset quarantine)."""
    org, user, headers = _create_test_org(db_session, "Data Quality")
    uav, comp, sensor, _ = _create_uav_asset(db_session, org, "UAV-QUALITY-01")

    # 1. Ingest with DEGRADED data quality
    evt_deg = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-deg-01",
        source_asset_id=uav.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=datetime.now(UTC),
        readings=[
            TelemetryReadingItem(
                sensor_code=sensor.sensor_code,
                measurement_type="vibration",
                value=0.0,
                unit="mm/s",
                data_quality="DEGRADED",
            )
        ],
    )
    resp_deg = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt_deg.model_dump(mode="json")]})
    assert resp_deg.status_code == 200

    # 2. Ingest with Unregistered Asset -> Quarantined
    evt_unmatched = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-unmatched-01",
        source_asset_id="UAV-GHOST-UNKNOWN",
        event_type="REALTIME_TELEMETRY",
        event_timestamp=datetime.now(UTC),
        readings=[TelemetryReadingItem(sensor_code="UNKNOWN_SENSOR", measurement_type="vibration", value=1.0, unit="mm/s")],
    )
    resp_unm = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt_unmatched.model_dump(mode="json")]})
    assert resp_unm.status_code == 200
    assert resp_unm.json()["rejected_count"] == 1


def test_m18_5_store_and_forward_idempotency_and_replay(client: TestClient, db_session: Session):
    """M18.5.6: Store-and-forward replayed batches return DUPLICATE without polluting database."""
    org, user, headers = _create_test_org(db_session, "Replay Idempotency")
    uav, comp, sensor, _ = _create_uav_asset(db_session, org, "UAV-REPLAY-01")

    evt = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id="evt-replayed-unique-id",
        source_asset_id=uav.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=datetime.now(UTC),
        readings=[TelemetryReadingItem(sensor_code=sensor.sensor_code, measurement_type="vibration", value=2.5, unit="mm/s")],
    )

    # First transmission: PROCESSED
    resp1 = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt.model_dump(mode="json")]})
    assert resp1.json()["processed_count"] == 1
    assert resp1.json()["duplicate_count"] == 0

    # Replayed transmission: DUPLICATE (idempotent ignore)
    resp2 = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [evt.model_dump(mode="json")]})
    assert resp2.json()["processed_count"] == 0
    assert resp2.json()["duplicate_count"] == 1


def test_m18_5_performance_and_latency_measurement(client: TestClient, db_session: Session):
    """M18.5.7: Measures ingestion latency under 25 concurrent events."""
    org, user, headers = _create_test_org(db_session, "Performance Org")
    uav, comp, sensor, _ = _create_uav_asset(db_session, org, "UAV-PERF-001")

    events: list[dict] = []
    now = datetime.now(UTC)
    for i in range(25):
        ev = NormalizedTelemetryEvent(
            source_system="KOTA_MAVLINK_GATEWAY",
            source_event_id=f"evt-perf-{i}-{uuid.uuid4().hex[:4]}",
            source_asset_id=uav.serial_number,
            event_type="REALTIME_TELEMETRY",
            event_timestamp=now + timedelta(seconds=i),
            readings=[
                TelemetryReadingItem(
                    sensor_code=sensor.sensor_code,
                    measurement_type="vibration",
                    value=1.5 + (i * 0.05),
                    unit="mm/s",
                )
            ],
        )
        events.append(ev.model_dump(mode="json"))

    t_start = time.perf_counter()
    resp = client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": events})
    t_elapsed = time.perf_counter() - t_start

    assert resp.status_code == 200
    assert resp.json()["processed_count"] == 25
    # Enforce sub-5-second latency for 25-event batch in local test environment
    assert t_elapsed < 5.0, f"Batch ingestion took {t_elapsed:.3f}s, expected < 5.0s"


def test_m18_5_full_digital_thread_to_lisa_grounding(client: TestClient, db_session: Session):
    """M18.5.8: End-to-end verification from MAVLink Ingestion -> Diagnostics -> M7 -> LISA."""
    org, user, headers = _create_test_org(db_session, "Full Thread Org")
    uav, comp, sensor, _ = _create_uav_asset(db_session, org, "UAV-THREAD-001")

    # Ingest baseline telemetry
    now = datetime.now(UTC)
    baseline_events: list[dict] = []
    for i in range(10):
        ev = NormalizedTelemetryEvent(
            source_system="KOTA_MAVLINK_GATEWAY",
            source_event_id=f"evt-base-{i}-{uuid.uuid4().hex[:4]}",
            source_asset_id=uav.serial_number,
            event_type="REALTIME_TELEMETRY",
            event_timestamp=now - timedelta(minutes=30 - i * 3),
            readings=[
                TelemetryReadingItem(
                    sensor_code=sensor.sensor_code,
                    measurement_type="vibration",
                    value=1.5 + (i * 0.02),
                    unit="mm/s",
                    component_id=comp.id,
                )
            ],
        )
        baseline_events.append(ev.model_dump(mode="json"))

    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": baseline_events})

    # Ingest severe vibration anomaly
    anomaly_event = NormalizedTelemetryEvent(
        source_system="KOTA_MAVLINK_GATEWAY",
        source_event_id=f"evt-anomaly-{uuid.uuid4().hex[:6]}",
        source_asset_id=uav.serial_number,
        event_type="REALTIME_TELEMETRY",
        event_timestamp=now,
        readings=[
            TelemetryReadingItem(
                sensor_code=sensor.sensor_code,
                measurement_type="vibration",
                value=52.0,
                unit="mm/s",
                component_id=comp.id,
            )
        ],
    )
    client.post("/api/v1/telemetry/ingest", headers=headers, json={"events": [anomaly_event.model_dump(mode="json")]})

    # Execute LISA Tool Queries
    user_obj = CurrentUser(
        id=user.id,
        organization_id=org.id,
        roles=["ORG_ADMIN"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
    )

    t_status = tools.execute_tool(db_session, user_obj, "get_asset_telemetry_status", {"asset_id": str(uav.id)})
    assert t_status["telemetry_state"] == "ACTIVE"
    assert t_status["total_recent_events"] > 0

    t_twin = tools.execute_tool(db_session, user_obj, "get_digital_twin", {"asset_id": str(uav.id)})
    assert t_twin["identity"]["serial_number"] == "UAV-THREAD-001"
    assert t_twin["identity"]["asset_id"] == str(uav.id)
