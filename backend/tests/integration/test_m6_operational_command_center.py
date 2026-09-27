import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.models.asset import Asset, AssetType
from app.models.battery import Battery, BatteryStatus
from app.models.component import Component
from app.models.installation_history import ComponentInstallation
from app.models.finding import Finding, FindingStatus, FindingSeverity
from app.models.flight import Flight
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.mission import Mission, MissionStatus
from app.models.organization import Organization
from app.models.user import User
from app.models.work_order import WorkOrder
from app.services import asset_service, flight_service, control_center_service


@pytest.fixture
def org_a(db_session: Session) -> Organization:
    org = Organization(name=f"Org A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"Org B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id,
        email=f"user-a-{uuid.uuid4().hex[:6]}@example.com",
        full_name="User A",
        hashed_password="hash",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_command_center_summary_fleet_health_and_activity(
    db_session: Session, org_a: Organization, user_a: User
):
    """M6-A & M6-K: Command Center Summary provides live grounded fleet health,
    operational activity, daily brief, and prioritized attention items."""
    # 1. Onboard 4 diverse assets: 1 Aircraft, 2 Drones, 1 eVTOL
    aircraft = Asset(
        organization_id=org_a.id,
        asset_type="AIRCRAFT",
        registration="VT-KOTA-1",
        manufacturer="Boeing",
        model="737-800",
        serial_number="MSN-33410",
        status="ACTIVE",
    )
    drone1 = Asset(
        organization_id=org_a.id,
        asset_type="DRONE",
        registration="DR-ALPHA",
        manufacturer="DJI",
        model="M300 RTK",
        serial_number="DJI-001",
        status="ACTIVE",
    )
    drone2 = Asset(
        organization_id=org_a.id,
        asset_type="DRONE",
        registration="DR-BETA",
        manufacturer="Skydio",
        model="X2D",
        serial_number="SKY-002",
        status="ACTIVE",
    )
    evtol = Asset(
        organization_id=org_a.id,
        asset_type="EVTOL",
        registration="VT-AIRTAXI",
        manufacturer="Archer",
        model="Midnight",
        serial_number="ARC-001",
        status="ACTIVE",
    )
    db_session.add_all([aircraft, drone1, drone2, evtol])
    db_session.commit()

    # 2. Add Baseline to Aircraft
    flight_service.create_asset_baseline(
        db_session,
        organization_id=org_a.id,
        actor_user_id=user_a.id,
        asset_id=aircraft.id,
        flight_hours=500.0,
        flight_cycles=250,
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="MIGRATION",
        notes="Historical airline baseline",
    )

    # 3. Log operational flights
    now = datetime.now(timezone.utc)
    flight_service.record_flight(
        db_session,
        organization_id=org_a.id,
        actor_user_id=user_a.id,
        asset_id=aircraft.id,
        flown_at=now,
        duration_minutes=120,
        cycles=1,
        flight_number="KT-101",
        origin="BOM",
        destination="BLR",
        update_battery=False,
    )
    flight_service.record_flight(
        db_session,
        organization_id=org_a.id,
        actor_user_id=user_a.id,
        asset_id=drone1.id,
        flown_at=now,
        duration_minutes=45,
        cycles=2,
        flight_number="DR-SRV-1",
        update_battery=False,
    )

    # 4. Add an open critical finding on drone2
    finding = Finding(
        organization_id=org_a.id,
        asset_id=drone2.id,
        title="Motor #3 Bearing Excessive Vibration",
        description="Vibration sensor flagged exceedance during pre-flight spool up.",
        severity="CRITICAL",
        status=FindingStatus.OPEN,
        discovered_at=now,
        discovered_by_user_id=user_a.id,
    )
    db_session.add(finding)

    # 5. Add an open work order on drone2
    wo = WorkOrder(
        organization_id=org_a.id,
        asset_id=drone2.id,
        title="Replace Motor #3 Propulsion Assembly",
        work_order_number="WO-DR2-001",
        status="IN_PROGRESS",
        priority="CRITICAL",
        due_at=now,
        created_by_user_id=user_a.id,
    )
    db_session.add(wo)
    db_session.commit()

    # 6. Evaluate Command Center Summary
    summary = control_center_service.get_summary(db_session, organization_id=org_a.id)

    # Verify Fleet Health
    assert summary.total_assets == 4
    assert summary.fleet_health is not None
    assert summary.fleet_health.total_assets == 4
    assert summary.fleet_health.asset_class_counts["AIRCRAFT"] == 1
    assert summary.fleet_health.asset_class_counts["DRONE"] == 2
    assert summary.fleet_health.asset_class_counts["EVTOL"] == 1
    assert summary.fleet_health.restricted_count >= 1  # drone2 under maintenance/grounded

    # Verify Operational Activity
    assert summary.operational_activity is not None
    assert summary.operational_activity.flights_today == 2
    assert summary.operational_activity.total_flights == 2
    # 500.0 baseline + 2.0 (120 min) + 0.75 (45 min) = 502.8 hrs
    assert summary.operational_activity.total_flight_hours >= 502.7
    # 250 baseline + 1 cyc + 2 cyc = 253 cyc
    assert summary.operational_activity.total_cycles == 253

    # Verify Attention Items
    assert len(summary.attention_items) >= 1
    top_item = summary.attention_items[0]
    assert top_item.priority == "CRITICAL"
    assert top_item.category in ("FINDING", "MAINTENANCE")

    # Verify Daily Brief
    assert summary.daily_brief is not None
    assert summary.daily_brief.total_assets == 4
    assert summary.daily_brief.attention_required_count >= 1
    assert len(summary.daily_brief.key_bullet_points) > 0


def test_command_center_fleet_operations_and_timeline(
    db_session: Session, org_a: Organization, user_a: User
):
    """M6-B & M6-D: Fleet Operations view and unified timeline stream."""
    asset = Asset(
        organization_id=org_a.id,
        asset_type="DRONE",
        registration="DR-SURVEY-99",
        manufacturer="Quantum",
        model="Tron",
        serial_number="QT-9901",
        status="ACTIVE",
    )
    db_session.add(asset)
    db_session.commit()

    now = datetime.now(timezone.utc)

    # Log flight
    flight_service.record_flight(
        db_session,
        organization_id=org_a.id,
        actor_user_id=user_a.id,
        asset_id=asset.id,
        flown_at=now,
        duration_minutes=60,
        cycles=1,
        flight_number="FL-99",
        update_battery=False,
    )

    # Install component
    comp = Component(
        organization_id=org_a.id,
        component_type="CAMERA",
        name="Sony A7R IV Mapping Sensor",
        serial_number="CAM-771",
        manufacturer="Sony",
    )
    db_session.add(comp)
    db_session.flush()

    ci = ComponentInstallation(
        organization_id=org_a.id,
        asset_id=asset.id,
        component_id=comp.id,
        installed_at=now,
        installed_by=user_a.id,
    )
    db_session.add(ci)
    db_session.commit()

    # Get fleet operations
    fleet_rows = control_center_service.get_fleet_operations(
        db_session, organization_id=org_a.id
    )
    assert len(fleet_rows) == 1
    row = fleet_rows[0]
    assert row.registration == "DR-SURVEY-99"
    assert row.asset_type == "DRONE"
    assert row.total_flight_hours == 1.0
    assert row.total_cycles == 1
    assert row.operational_state == "AVAILABLE"
    assert row.readiness_state == "READY"

    # Get fleet timeline
    timeline = control_center_service.get_fleet_timeline(
        db_session, organization_id=org_a.id
    )
    assert len(timeline) >= 2
    event_types = [e.event_type for e in timeline]
    assert "FLIGHT_SORTIE" in event_types
    assert "COMPONENT_INSTALLATION" in event_types


def test_command_center_tenant_isolation(
    db_session: Session, org_a: Organization, org_b: Organization, user_a: User
):
    """M6-P: Organization isolation strictly preserved for command center."""
    asset_a = Asset(
        organization_id=org_a.id,
        asset_type="AIRCRAFT",
        registration="VT-ORG-A",
        status="ACTIVE",
    )
    asset_b = Asset(
        organization_id=org_b.id,
        asset_type="AIRCRAFT",
        registration="VT-ORG-B",
        status="ACTIVE",
    )
    db_session.add_all([asset_a, asset_b])
    db_session.commit()

    summary_a = control_center_service.get_summary(db_session, organization_id=org_a.id)
    summary_b = control_center_service.get_summary(db_session, organization_id=org_b.id)

    assert summary_a.total_assets == 1
    assert summary_b.total_assets == 1

    ops_a = control_center_service.get_fleet_operations(db_session, organization_id=org_a.id)
    ops_b = control_center_service.get_fleet_operations(db_session, organization_id=org_b.id)

    assert len(ops_a) == 1
    assert ops_a[0].registration == "VT-ORG-A"
    assert len(ops_b) == 1
    assert ops_b[0].registration == "VT-ORG-B"
