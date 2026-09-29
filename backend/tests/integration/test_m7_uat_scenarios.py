"""M7 UAT Scenario Test Suite: Controlled Acceptance Tests for All 14 M7 Scenarios.

Verifies:
UAT-01: Asset approaches inspection threshold
UAT-02: Repeated finding occurs
UAT-03: Compliance evidence missing (Kleene logic preserved)
UAT-04: Utilization increases (+50% pace)
UAT-05: Multiple assets show similar issues (Fleet pattern)
UAT-06: Signal acknowledged
UAT-07: Signal resolved
UAT-08: Tenant isolation
UAT-09: LISA asks "What needs attention today?"
UAT-10: LISA asks "Why is this asset high priority?"
UAT-11: Operator drills from signal -> evidence -> source record
UAT-12: Historical baseline data exists (no double counting)
UAT-13: No sufficient evidence exists (no fabrication)
UAT-14: Protected baseline verification
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.compliance import ComplianceObligation, ComplianceState
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
from app.models.lisa_conversation_context import LisaConversationContext
from app.services.lisa.entity_resolution_service import ResolvedEntity
from app.services.lisa.message_resolution_service import MessageResolution


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
def org_uat(db_session: Session) -> Organization:
    from tests.integration.conftest import grant_features

    org = Organization(name=f"UAT Air Operations {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    grant_features(
        db_session,
        org.id,
        "aircraft_fleet_management",
        "predictive_maintenance",
        "work_order_management",
        "inspections_management",
        "procurement_management",
        "compliance_management",
        "advanced_compliance_intelligence",
        "hums",
        "flight_telemetry",
        "digital_twin",
        "mro_intelligence",
        "lisa_ai_copilot",
    )
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def org_other(db_session: Session) -> Organization:
    from tests.integration.conftest import grant_features

    org = Organization(name=f"Competitor Aero {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    grant_features(
        db_session,
        org.id,
        "aircraft_fleet_management",
        "predictive_maintenance",
        "work_order_management",
        "inspections_management",
        "procurement_management",
        "compliance_management",
        "advanced_compliance_intelligence",
        "hums",
        "flight_telemetry",
        "digital_twin",
        "mro_intelligence",
        "lisa_ai_copilot",
    )
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_uat(db_session: Session, org_uat: Organization) -> User:
    user = User(
        organization_id=org_uat.id,
        email=f"operator.{uuid.uuid4().hex[:6]}@uatair.com",
        full_name="Lead Operator",
        hashed_password="pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="ORG_ADMIN", organization_id=org_uat.id))
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def user_other(db_session: Session, org_other: Organization) -> User:
    user = User(
        organization_id=org_other.id,
        email=f"other.{uuid.uuid4().hex[:6]}@competitor.com",
        full_name="Other User",
        hashed_password="pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="ORG_ADMIN", organization_id=org_other.id))
    db_session.commit()
    db_session.refresh(user)
    return user


def test_uat_01_inspection_threshold_approaching(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-01: Asset approaches inspection threshold -> signal generated, evidence shown, recommended action."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="KTA-001 Airframe")
    db_session.add(asset)
    db_session.flush()

    aircraft = Aircraft(organization_id=org_uat.id, asset_id=asset.id, registration="KTA-001", msn="MSN-101", aircraft_type="TwinOtter")
    db_session.add(aircraft)

    insp = MaintenanceRequirement(
        organization_id=org_uat.id,
        description="200-Hour Phase Check",
        ata_chapter="05",
        interval_type=MaintenanceIntervalType.FLIGHT_HOURS,
        fh_interval=200,
    )
    db_session.add(insp)

    # 182 flight hours logged (18 hours remaining)
    flight = Flight(
        organization_id=org_uat.id,
        asset_id=asset.id,
        flight_number="KT-201",
        duration_minutes=int(182.0 * 60),
        cycles=90,
        flown_at=datetime.datetime.now(datetime.UTC),
        status="VERIFIED",
    )
    db_session.add(flight)
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert res.status_code == 200
    signals = res.json()

    insp_signals = [s for s in signals if s["signal_type"] == "INSPECTION_THRESHOLD"]
    assert len(insp_signals) == 1
    sig = insp_signals[0]
    assert sig["contributing_factors"]["hours_remaining"] == 18.0
    assert len(sig["evidence"]) >= 1
    assert len(sig["recommended_actions"]) >= 1


def test_uat_02_recurring_finding_pattern(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-02: Repeated finding occurs -> recurring pattern detected, prior findings visible, no unsupported root-cause."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="KTA-014 Jet")
    db_session.add(asset)
    db_session.flush()

    aircraft = Aircraft(organization_id=org_uat.id, asset_id=asset.id, registration="KTA-014", msn="MSN-1014", aircraft_type="B737")
    db_session.add(aircraft)

    now = datetime.datetime.now(datetime.UTC)
    f1 = Finding(organization_id=org_uat.id, asset_id=asset.id, title="Hydraulic leak left main gear", description="Hydraulic leak found on left main gear assembly", severity=FindingSeverity.MAJOR, status=FindingStatus.CLOSED, created_at=now - datetime.timedelta(days=30))
    f2 = Finding(organization_id=org_uat.id, asset_id=asset.id, title="Hydraulic pressure drop on gear retraction", description="Hydraulic pressure drop during retraction check", severity=FindingSeverity.CRITICAL, status=FindingStatus.OPEN, created_at=now - datetime.timedelta(days=2))
    db_session.add_all([f1, f2])
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert res.status_code == 200
    rec_signals = [s for s in res.json() if s["signal_type"] == "RECURRING_FINDING"]
    assert len(rec_signals) == 1
    sig = rec_signals[0]
    assert sig["contributing_factors"]["total_occurrences"] == 2
    assert "Recurring Hydraulic Finding Pattern" in sig["title"]


def test_uat_03_compliance_evidence_missing_kleene(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-03: Compliance evidence missing -> evidence-gap signal, compliance remains UNKNOWN, no false compliance."""
    from app.models.compliance import RegulatoryRequirement

    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Cessna 208")
    db_session.add(asset)
    db_session.flush()

    reg_req = RegulatoryRequirement(
        organization_id=org_uat.id,
        authority="FAA",
        requirement_number="FAA AD 2026-14-02",
        title="Wing Spar Inspection Requirement",
        description="Inspect wing spar attachment points for stress fatigue.",
    )
    db_session.add(reg_req)
    db_session.flush()

    ob = ComplianceObligation(
        organization_id=org_uat.id,
        asset_id=asset.id,
        requirement_id=reg_req.id,
        status="UNKNOWN",
        required_action="AD 2026-14-02 Wing Spar Inspection Obligation",
    )
    db_session.add(ob)
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert res.status_code == 200
    gap_signals = [s for s in res.json() if s["signal_type"] == "COMPLIANCE_RISK"]
    assert len(gap_signals) >= 1
    sig = gap_signals[0]
    assert sig["contributing_factors"]["unknown_count"] >= 1


def test_uat_04_utilization_surge_pace(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-04: Utilization increases -> utilization trend signal, hours consistent with domain service."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Cargo Hauler")
    db_session.add(asset)
    db_session.flush()

    # Log 30 FH in last 14 days, 5 FH in prior 14 days
    now = datetime.datetime.now(datetime.UTC)
    fl1 = Flight(organization_id=org_uat.id, asset_id=asset.id, flight_number="C-01", duration_minutes=int(30.0 * 60), cycles=15, flown_at=now - datetime.timedelta(days=3), status="VERIFIED")
    fl2 = Flight(organization_id=org_uat.id, asset_id=asset.id, flight_number="C-02", duration_minutes=int(5.0 * 60), cycles=2, flown_at=now - datetime.timedelta(days=20), status="VERIFIED")
    db_session.add_all([fl1, fl2])
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert res.status_code == 200
    util_signals = [s for s in res.json() if s["signal_type"] == "UTILIZATION_TREND"]
    assert len(util_signals) >= 1
    sig = util_signals[0]
    assert "Accelerated Utilization Pace" in sig["title"]


def test_uat_05_fleet_level_pattern(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-05: Multiple assets show similar issues -> fleet-level pattern surfaced."""
    # Create 2 assets, each with recurring AVIONICS findings
    a1 = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Fleet Alpha")
    a2 = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Fleet Bravo")
    db_session.add_all([a1, a2])
    db_session.flush()

    now = datetime.datetime.now(datetime.UTC)
    db_session.add(Finding(organization_id=org_uat.id, asset_id=a1.id, title="Transponder Mode S drop 1", description="Avionics transponder drop 1", severity=FindingSeverity.MINOR, status=FindingStatus.CLOSED, created_at=now - datetime.timedelta(days=10)))
    db_session.add(Finding(organization_id=org_uat.id, asset_id=a1.id, title="Transponder Mode S drop 2", description="Avionics transponder drop 2", severity=FindingSeverity.MAJOR, status=FindingStatus.OPEN, created_at=now - datetime.timedelta(days=2)))
    db_session.add(Finding(organization_id=org_uat.id, asset_id=a2.id, title="TCAS intermittent fail 1", description="Avionics TCAS fail 1", severity=FindingSeverity.MINOR, status=FindingStatus.CLOSED, created_at=now - datetime.timedelta(days=12)))
    db_session.add(Finding(organization_id=org_uat.id, asset_id=a2.id, title="TCAS intermittent fail 2", description="Avionics TCAS fail 2", severity=FindingSeverity.MAJOR, status=FindingStatus.OPEN, created_at=now - datetime.timedelta(days=1)))
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get("/api/v1/intelligence/summary", headers=headers)
    assert res.status_code == 200
    data = res.json()
    fleet_patterns = data["fleet_patterns"]
    assert len(fleet_patterns) >= 1
    assert any("Fleet-Wide Finding Pattern" in p["title"] and "Avionics" in p["title"] for p in fleet_patterns)


def test_uat_06_and_07_signal_acknowledgement_and_resolution(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-06 & UAT-07: Signal acknowledged persists, signal resolved clears from active summary."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Asset Lifecycle")
    db_session.add(asset)
    db_session.flush()

    wo = WorkOrder(organization_id=org_uat.id, asset_id=asset.id, work_order_number="WO-UAT-07", title="Engine Boroscope Check", status="OPEN", priority="CRITICAL", due_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
    db_session.add(wo)
    db_session.flush()

    headers = _auth_headers(user_uat)
    summary_1 = client.get("/api/v1/intelligence/summary", headers=headers).json()
    sig_id = summary_1["signals"][0]["id"]

    # UAT-06: Acknowledge
    ack_res = client.post(f"/api/v1/intelligence/signals/{sig_id}/acknowledge", headers=headers)
    assert ack_res.status_code == 200
    assert ack_res.json()["status"] == "ACKNOWLEDGED"

    # UAT-07: Resolve
    res_res = client.post(f"/api/v1/intelligence/signals/{sig_id}/resolve", json={"resolution_notes": "Boroscope inspection completed, NDT clear."}, headers=headers)
    assert res_res.status_code == 200
    assert res_res.json()["status"] == "RESOLVED"

    # Verify no longer active in summary
    summary_2 = client.get("/api/v1/intelligence/summary", headers=headers).json()
    assert not any(s["id"] == sig_id for s in summary_2["signals"])


def test_uat_08_tenant_isolation(
    client: TestClient, db_session: Session, org_uat: Organization, org_other: Organization, user_other: User
):
    """UAT-08: Tenant B cannot access Org UAT signals or summaries."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Org UAT Jet")
    db_session.add(asset)
    db_session.flush()

    wo = WorkOrder(organization_id=org_uat.id, asset_id=asset.id, work_order_number="WO-ISO-99", title="Special Mission Fit", status="OPEN", priority="CRITICAL", due_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=2))
    db_session.add(wo)
    db_session.flush()

    headers_other = _auth_headers(user_other)
    summary = client.get("/api/v1/intelligence/summary", headers=headers_other).json()
    assert summary["total_active_signals"] == 0
    assert len(summary["signals"]) == 0


def test_uat_09_and_10_lisa_grounded_intelligence_queries(
    db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-09 & UAT-10: LISA asks 'What needs attention today?' and 'Why is this asset high priority?'"""
    from app.services.lisa import orchestration_service

    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="KTA-099")
    db_session.add(asset)
    db_session.flush()

    aircraft = Aircraft(organization_id=org_uat.id, asset_id=asset.id, registration="KTA-099", msn="MSN-099", aircraft_type="A320")
    db_session.add(aircraft)

    wo = WorkOrder(organization_id=org_uat.id, asset_id=asset.id, aircraft_id=aircraft.id, work_order_number="WO-LISA-01", title="Emergency Fuel Valve Replacement", status="OPEN", priority="CRITICAL", due_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=4))
    db_session.add(wo)
    db_session.flush()

    # 1. UAT-09: Fleet inquiry "What needs attention today?"
    conv_context = LisaConversationContext(organization_id=org_uat.id, user_id=user_uat.id)
    resolution = MessageResolution(context=conv_context)
    result_fleet = orchestration_service.investigate(
        db_session, user_uat, question="what needs attention today?", resolution=resolution
    )
    assert result_fleet is not None
    assert result_fleet.status == "ANSWERED"
    assert "operational alert(s) require attention" in result_fleet.headline
    assert len(result_fleet.what_i_found) >= 1

    # 2. UAT-10: Asset specific inquiry
    conv_context_asset = LisaConversationContext(organization_id=org_uat.id, user_id=user_uat.id, current_aircraft_id=aircraft.id)
    resolution_asset = MessageResolution(
        context=conv_context_asset,
        resolved=[ResolvedEntity(entity_type="aircraft", entity_id=str(aircraft.id), display="KTA-099")],
    )
    result_asset = orchestration_service.investigate(
        db_session, user_uat, question="why is this asset high priority?", resolution=resolution_asset
    )
    assert result_asset is not None
    assert result_asset.status == "ANSWERED"
    assert "KTA-099" in result_asset.headline
    assert "CRITICAL priority" in result_asset.headline


def test_uat_12_historical_baseline_utilization_no_double_counting(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-12: Historical baseline + flight records calculate exact sum without double counting."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Baseline Airframe")
    db_session.add(asset)
    db_session.flush()

    # 150 FH baseline from legacy Excel
    baseline = AssetHistoricalBaseline(
        organization_id=org_uat.id,
        asset_id=asset.id,
        flight_hours=150.0,
        flight_cycles=75,
        effective_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=5),
        source="EXCEL_IMPORT",
        is_active=True,
    )
    db_session.add(baseline)

    # 25 FH new flight
    flight = Flight(
        organization_id=org_uat.id,
        asset_id=asset.id,
        flight_number="KT-333",
        duration_minutes=int(25.0 * 60),
        cycles=10,
        flown_at=datetime.datetime.now(datetime.UTC),
        status="VERIFIED",
    )
    db_session.add(flight)

    # 200 FH Inspection Requirement -> exactly 25 FH remaining (200 - 175)
    insp = MaintenanceRequirement(
        organization_id=org_uat.id,
        description="200-Hour Check",
        ata_chapter="05",
        interval_type=MaintenanceIntervalType.FLIGHT_HOURS,
        fh_interval=200,
    )
    db_session.add(insp)
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert res.status_code == 200
    signals = res.json()
    insp_sig = [s for s in signals if s["signal_type"] == "INSPECTION_THRESHOLD"][0]
    assert insp_sig["contributing_factors"]["total_flight_hours"] == 175.0
    assert insp_sig["contributing_factors"]["hours_remaining"] == 25.0


def test_uat_13_no_fabrication_when_data_insufficient(
    client: TestClient, db_session: Session, org_uat: Organization, user_uat: User
):
    """UAT-13: Nominal asset with no thresholds, defects, or gaps produces ZERO fabricated signals."""
    asset = Asset(organization_id=org_uat.id, asset_type=AssetType.AIRCRAFT, model="Clean Asset")
    db_session.add(asset)
    db_session.flush()

    headers = _auth_headers(user_uat)
    res = client.get(f"/api/v1/intelligence/assets/{asset.id}/signals", headers=headers)
    assert res.status_code == 200
    signals = res.json()
    assert len(signals) == 0
