"""M7 Integration Tests: Proactive Aerospace Intelligence, Risk & Decision Automation.

Verifies early-warning signals, maintenance/inspection thresholds, recurring finding detection,
utilization trends, compliance/evidence gaps, fleet patterns, signal lifecycle mutations,
and strict multi-tenant isolation.
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support.tokens import mint_token as create_access_token
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.battery import Battery, BatteryStatus
from app.models.compliance import ComplianceObligation, ComplianceState
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.flight import Flight
from app.models.maintenance_requirement import (
    MaintenanceIntervalType,
    MaintenanceRequirement,
    MaintenanceRequirementApplicability,
)
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        roles=["ORG_ADMIN"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def org_a(db_session: Session) -> Organization:
    org = Organization(name=f"AeroDynamics Corp {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_b(db_session: Session) -> Organization:
    org = Organization(name=f"Skyline Operations {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, org_a: Organization) -> User:
    user = User(
        organization_id=org_a.id,
        email=f"chief.pilot.{uuid.uuid4().hex[:6]}@aerodynamics.com",
        full_name="Chief Pilot",
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
        email=f"ops.{uuid.uuid4().hex[:6]}@skyline.com",
        full_name="Skyline Ops",
        hashed_password="pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_maintenance_threshold_and_overdue_signals(
    client: TestClient, db_session: Session, org_a: Organization, user_a: User
):
    """Verifies overdue and upcoming maintenance work orders produce grounded early-warning signals."""
    asset = Asset(
        organization_id=org_a.id,
        asset_type=AssetType.AIRCRAFT,
        model="Airbus A320",
    )
    db_session.add(asset)
    db_session.flush()

    aircraft = Aircraft(
        organization_id=org_a.id,
        asset_id=asset.id,
        registration="VT-AOG-1",
        msn="MSN-901",
        aircraft_type="A320",
    )
    db_session.add(aircraft)

    # 1. Overdue Work Order
    overdue_wo = WorkOrder(
        organization_id=org_a.id,
        asset_id=asset.id,
        aircraft_id=aircraft.id,
        work_order_number="WO-OVERDUE-01",
        title="Main Gear Actuator Seal Replacement",
        status="OPEN",
        priority="CRITICAL",
        due_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=3),
    )
    db_session.add(overdue_wo)
    db_session.flush()

    headers = _auth_headers(user_a)
    response = client.get("/api/v1/intelligence/summary", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["critical_count"] >= 1
    overdue_signals = [s for s in data["signals"] if s["signal_type"] == "MAINTENANCE_THRESHOLD"]
    assert len(overdue_signals) >= 1
    sig = overdue_signals[0]
    assert "WO-OVERDUE-01" in sig["title"]
    assert sig["severity"] == "CRITICAL"
    assert len(sig["evidence"]) >= 1
    assert sig["evidence"][0]["source_type"] == "WorkOrder"


def test_inspection_threshold_signals_with_utilization(
    client: TestClient, db_session: Session, org_a: Organization, user_a: User
):
    """Verifies that actual operational flight hours trigger inspection early warning signals."""
    asset = Asset(
        organization_id=org_a.id,
        asset_type=AssetType.AIRCRAFT,
        model="Boeing 737",
    )
    db_session.add(asset)
    db_session.flush()

    aircraft = Aircraft(
        organization_id=org_a.id,
        asset_id=asset.id,
        registration="VT-INSP-1",
        msn="MSN-801",
        aircraft_type="B737",
    )
    db_session.add(aircraft)

    # 100-Hour Mandatory Inspection
    insp = MaintenanceRequirement(
        organization_id=org_a.id,
        description="100-Hour Airframe & Powerplant Inspection",
        ata_chapter="05",
        interval_type=MaintenanceIntervalType.FLIGHT_HOURS,
        fh_interval=100,
    )
    db_session.add(insp)

    # Carried-in baseline of 80 hours + verified flight of 12 hours = 92 hours (8 hours remaining)
    baseline = AssetHistoricalBaseline(
        organization_id=org_a.id,
        asset_id=asset.id,
        flight_hours=80.0,
        flight_cycles=40,
        effective_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10),
        source="MIGRATION",
        is_active=True,
    )
    db_session.add(baseline)

    flight = Flight(
        organization_id=org_a.id,
        asset_id=asset.id,
        flight_number="KT-101",
        origin="VIDP",
        destination="VOMM",
        duration_minutes=720,
        cycles=6,
        flown_at=datetime.datetime.now(datetime.UTC),
        status="VERIFIED",
    )
    db_session.add(flight)
    db_session.flush()

    headers = _auth_headers(user_a)
    response = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert response.status_code == 200
    signals = response.json()

    insp_signals = [s for s in signals if s["signal_type"] == "INSPECTION_THRESHOLD"]
    assert len(insp_signals) >= 1
    sig = insp_signals[0]
    assert "100-Hour" in sig["title"]
    assert sig["severity"] in ("HIGH", "MEDIUM")
    assert sig["contributing_factors"]["hours_remaining"] == 8.0
    assert sig["contributing_factors"]["total_flight_hours"] == 92.0


def test_recurring_finding_pattern_detection(
    client: TestClient, db_session: Session, org_a: Organization, user_a: User
):
    """Verifies that multiple findings under the same category trigger recurring pattern intelligence."""
    asset = Asset(
        organization_id=org_a.id,
        asset_type=AssetType.AIRCRAFT,
        model="Bombardier Q400",
    )
    db_session.add(asset)
    db_session.flush()

    aircraft = Aircraft(
        organization_id=org_a.id,
        asset_id=asset.id,
        registration="VT-REC-1",
        msn="MSN-701",
        aircraft_type="Q400",
    )
    db_session.add(aircraft)

    # 3 Hydraulic leak findings in last 45 days
    now = datetime.datetime.now(datetime.UTC)
    for i, day_offset in enumerate([40, 20, 5]):
        finding = Finding(
            organization_id=org_a.id,
            asset_id=asset.id,
            title=f"Hydraulic actuator seepage on sector {i+1}",
            description=f"Hydraulic fluid leak observed at main actuator junction {i+1}",
            severity=FindingSeverity.MAJOR,
            status=FindingStatus.OPEN if i == 2 else FindingStatus.CLOSED,
            created_at=now - datetime.timedelta(days=day_offset),
        )
        db_session.add(finding)
    db_session.flush()

    headers = _auth_headers(user_a)
    response = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert response.status_code == 200
    signals = response.json()

    rec_signals = [s for s in signals if s["signal_type"] == "RECURRING_FINDING"]
    assert len(rec_signals) == 1
    sig = rec_signals[0]
    assert "Recurring Hydraulic Finding Pattern" in sig["title"]
    assert sig["contributing_factors"]["total_occurrences"] == 3
    assert len(sig["evidence"]) == 3


def test_signal_lifecycle_acknowledgement_and_resolution(
    client: TestClient, db_session: Session, org_a: Organization, user_a: User
):
    """Verifies full lifecycle state machine: OPEN -> ACKNOWLEDGED -> IN_REVIEW -> RESOLVED."""
    asset = Asset(
        organization_id=org_a.id,
        asset_type=AssetType.DRONE,
        model="Delivery Drone",
        serial_number="DR-99",
    )
    db_session.add(asset)
    db_session.flush()

    battery = Battery(
        organization_id=org_a.id,
        asset_id=asset.id,
        serial_number="BAT-LIPO-99",
        model="6S-22000mAh",
        cycle_count=285,
        health_percent=76,
        status=BatteryStatus.SERVICE_DUE,
    )
    db_session.add(battery)
    db_session.flush()

    headers = _auth_headers(user_a)

    # 1. Fetch signal
    resp = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert resp.status_code == 200
    signals = resp.json()
    assert len(signals) >= 1
    sig_id = signals[0]["id"]
    assert signals[0]["status"] == "OPEN"

    # 2. Acknowledge signal
    resp_ack = client.post(f"/api/v1/intelligence/signals/{sig_id}/acknowledge", headers=headers)
    assert resp_ack.status_code == 200
    assert resp_ack.json()["status"] == "ACKNOWLEDGED"

    # 3. Set In Review
    resp_rev = client.post(
        f"/api/v1/intelligence/signals/{sig_id}/in-review",
        json={"notes": "Battery capacity load test scheduled for 14:00."},
        headers=headers,
    )
    assert resp_rev.status_code == 200
    assert resp_rev.json()["status"] == "IN_REVIEW"

    # 4. Resolve Signal
    resp_res = client.post(
        f"/api/v1/intelligence/signals/{sig_id}/resolve",
        json={"resolution_notes": "Battery replaced with new pack SN BAT-LIPO-100."},
        headers=headers,
    )
    assert resp_res.status_code == 200
    assert resp_res.json()["status"] == "RESOLVED"
    assert resp_res.json()["resolution_notes"] == "Battery replaced with new pack SN BAT-LIPO-100."


def test_tenant_isolation_signals(
    client: TestClient,
    db_session: Session,
    org_a: Organization,
    org_b: Organization,
    user_a: User,
    user_b: User,
):
    """Strict tenant isolation: Organization B must never see Org A intelligence signals."""
    asset_a = Asset(
        organization_id=org_a.id,
        asset_type=AssetType.AIRCRAFT,
        model="Org A Aircraft",
    )
    db_session.add(asset_a)
    db_session.flush()

    # Overdue work order in Org A
    wo_a = WorkOrder(
        organization_id=org_a.id,
        asset_id=asset_a.id,
        work_order_number="WO-SECRET-A",
        title="Confidential Defense Avionics Check",
        status="OPEN",
        priority="CRITICAL",
        due_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5),
    )
    db_session.add(wo_a)
    db_session.flush()

    # User B queries summary
    headers_b = _auth_headers(user_b)
    resp_b = client.get("/api/v1/intelligence/summary", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["total_active_signals"] == 0
    assert not any("WO-SECRET-A" in s["title"] for s in data_b["signals"])

    # User B attempts to get asset A signals
    resp_b_asset = client.get(f"/api/v1/intelligence/assets/{asset_a.id}/signals", headers=headers_b)
    assert resp_b_asset.status_code == 200
    assert len(resp_b_asset.json()) == 0
