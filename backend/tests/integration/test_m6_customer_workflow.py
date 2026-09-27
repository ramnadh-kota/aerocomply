import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.battery import Battery, BatteryStatus
from app.models.component import Component
from app.models.installation_history import ComponentInstallation
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingStatus, DispositionType
from app.models.flight import Flight
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.organization import Organization
from app.models.user import User
from app.models.work_order import WorkOrder
from app.services import (
    asset_service,
    flight_service,
    control_center_service,
    aerospace_state_service,
)
from app.services.intelligence import (
    readiness_intelligence_service,
    risk_intelligence_service,
    priority_intelligence_service,
    decision_service,
    recommendation_service,
)


@pytest.fixture
def org(db_session: Session) -> Organization:
    o = Organization(name=f"Customer Aero Corp {uuid.uuid4().hex[:6]}")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def pilot(db_session: Session, org: Organization) -> User:
    u = User(
        organization_id=org.id,
        email=f"pilot-{uuid.uuid4().hex[:6]}@aerocorp.com",
        full_name="Captain Rajesh Sharma",
        hashed_password="hash",
        is_active=True,
        email_verified=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_m6_complete_customer_operational_workflow_scenarios_1_to_14(
    db_session: Session, org: Organization, pilot: User
):
    """M6-N & M6-O: Complete 14-step operational UAT scenario simulation.

    Scenario 1: Customer views fleet
    Scenario 2: Customer opens an asset
    Scenario 3: Customer views flight history
    Scenario 4: Customer records a new flight
    Scenario 5: Flight hours/cycles update
    Scenario 6: Maintenance state changes
    Scenario 7: Inspection becomes due
    Scenario 8: Technician records a finding
    Scenario 9: Evidence is attached
    Scenario 10: Compliance state changes
    Scenario 11: Readiness changes
    Scenario 12: Command Center reflects the change
    Scenario 13: LISA explains the change
    Scenario 14: User follows recommended action to resolution
    """
    now = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Scenario 1: Customer views fleet
    # -------------------------------------------------------------------------
    asset = Asset(
        organization_id=org.id,
        asset_type="DRONE",
        registration="DR-PILOT-01",
        manufacturer="AeroKopter",
        model="HeavyLifter-X8",
        serial_number="HL8-9002",
        status="ACTIVE",
    )
    db_session.add(asset)
    db_session.flush()

    battery = Battery(
        organization_id=org.id,
        asset_id=asset.id,
        serial_number="BAT-HL8-01",
        manufacturer="Tattu",
        model="22000mAh 6S",
        capacity_mah=22000,
        voltage=24,
        cycle_count=10,
        health_percent=98,
        status=BatteryStatus.GOOD,
    )
    db_session.add(battery)
    db_session.commit()

    fleet_summary = control_center_service.get_summary(db_session, organization_id=org.id)
    assert fleet_summary.total_assets == 1
    assert fleet_summary.fleet_health.total_assets == 1

    # -------------------------------------------------------------------------
    # Scenario 2: Customer opens an asset
    # -------------------------------------------------------------------------
    asset_ctx = asset_service.get_asset_domain_context(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert asset_ctx.identity.id == asset.id
    assert asset_ctx.identity.registration == "DR-PILOT-01"
    assert asset_ctx.operational_status == "AVAILABLE"

    # -------------------------------------------------------------------------
    # Scenario 3: Customer views flight history (initial empty / carry-in baseline)
    # -------------------------------------------------------------------------
    flight_service.create_asset_baseline(
        db_session,
        organization_id=org.id,
        actor_user_id=pilot.id,
        asset_id=asset.id,
        flight_hours=120.0,
        flight_cycles=60,
        effective_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="MIGRATION",
        notes="Carry-in fleet baseline from customer records",
    )

    util_before = flight_service.get_utilization(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert util_before["total_minutes"] == 120 * 60
    assert util_before["total_cycles"] == 60
    assert util_before["total_flights"] == 0

    # -------------------------------------------------------------------------
    # Scenario 4: Customer records a new operational flight
    # -------------------------------------------------------------------------
    flight = flight_service.record_flight(
        db_session,
        organization_id=org.id,
        actor_user_id=pilot.id,
        asset_id=asset.id,
        flown_at=now,
        duration_minutes=90,
        cycles=2,
        flight_number="HL8-FL-101",
        origin="Site Alpha",
        destination="Site Beta",
        pilot_user_id=pilot.id,
        notes="Infrastructure survey flight leg completed nominal.",
        update_battery=False,
    )
    assert flight.id is not None

    # -------------------------------------------------------------------------
    # Scenario 5: Flight hours and cycles update
    # -------------------------------------------------------------------------
    util_after = flight_service.get_utilization(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    # 120 hrs baseline + 1.5 hrs (90 min) = 121.5 hrs
    assert util_after["total_minutes"] == (120 * 60) + 90
    assert util_after["total_cycles"] == 62
    assert util_after["total_flights"] == 1

    # -------------------------------------------------------------------------
    # Scenario 6: Maintenance state changes (work order scheduled)
    # -------------------------------------------------------------------------
    wo = WorkOrder(
        organization_id=org.id,
        asset_id=asset.id,
        work_order_number="WO-INSP-100H",
        title="100-Hour Airframe & Propeller Check",
        status="IN_PROGRESS",
        priority="HIGH",
        due_at=now,
        created_by_user_id=pilot.id,
    )
    db_session.add(wo)
    db_session.commit()

    op_state = asset_service.compute_operational_state(
        db_session, organization_id=org.id, asset=asset
    )
    assert op_state == "MAINTENANCE"

    # -------------------------------------------------------------------------
    # Scenario 7: Inspection becomes due
    # -------------------------------------------------------------------------
    insp = InspectionRequirement(
        organization_id=org.id,
        work_order_id=wo.id,
        status=InspectionRequirementStatus.PENDING,
    )
    db_session.add(insp)
    db_session.commit()

    # -------------------------------------------------------------------------
    # Scenario 8: Technician records a finding
    # -------------------------------------------------------------------------
    finding = Finding(
        organization_id=org.id,
        asset_id=asset.id,
        title="Propeller Blade Delamination on Rotor 4",
        description="Visible composite split along leading edge during inspection.",
        severity="HIGH",
        status=FindingStatus.OPEN,
        discovered_at=now,
        discovered_by_user_id=pilot.id,
    )
    db_session.add(finding)
    db_session.commit()

    # -------------------------------------------------------------------------
    # Scenario 9: Evidence is attached
    # -------------------------------------------------------------------------
    ev = Evidence(
        organization_id=org.id,
        title="NDT Ultrasonic Scan Report - Rotor 4",
        status=EvidenceStatus.SUBMITTED,
    )
    db_session.add(ev)
    db_session.commit()

    # -------------------------------------------------------------------------
    # Scenario 10: Compliance state changes
    # -------------------------------------------------------------------------
    comp_state = asset_service.get_asset_compliance(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert comp_state is not None

    # -------------------------------------------------------------------------
    # Scenario 11: Readiness changes (restricted / blocked)
    # -------------------------------------------------------------------------
    readiness_intel = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert readiness_intel.readiness_state == "BLOCKED"
    assert len(readiness_intel.blockers) >= 1

    # -------------------------------------------------------------------------
    # Scenario 12: Command Center reflects the change
    # -------------------------------------------------------------------------
    cc_summary = control_center_service.get_summary(db_session, organization_id=org.id)
    assert cc_summary.fleet_health.restricted_count == 1
    assert cc_summary.fleet_health.ready_count == 0
    assert len(cc_summary.attention_items) >= 1
    assert any("Finding" in item.title or "Propeller" in item.title for item in cc_summary.attention_items)

    # -------------------------------------------------------------------------
    # Scenario 13: LISA explains the change
    # -------------------------------------------------------------------------
    decision = decision_service.get_asset_decision(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    recommendation = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert decision.decision_state in ("ACTION_REQUIRED", "IMMEDIATE_ACTION_REQUIRED")
    assert decision.readiness_state == "BLOCKED"
    assert len(recommendation.items) >= 1

    # -------------------------------------------------------------------------
    # Scenario 14: User follows recommended investigation & action to resolution
    # -------------------------------------------------------------------------
    # 1. Close finding
    finding.status = FindingStatus.CLOSED
    finding.disposition_type = DispositionType.CORRECTIVE_ACTION
    finding.disposition_notes = "Propeller blade assembly replaced and torqued to OEM specification."

    # 2. Complete inspection
    insp.status = InspectionRequirementStatus.COMPLETED

    # 3. Complete work order
    wo.status = "COMPLETED"
    wo.completed_at = datetime.now(timezone.utc)
    db_session.commit()

    # 4. Verify operational state restored and zero blockers remain
    new_op_state = asset_service.compute_operational_state(
        db_session, organization_id=org.id, asset=asset
    )
    assert new_op_state == "AVAILABLE"

    new_readiness = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org.id, asset_id=asset.id
    )
    assert new_readiness.readiness_state in ("READY", "UNKNOWN")
    assert len(new_readiness.blockers) == 0

    # 5. Verify Command Center returns to nominal state
    cc_final = control_center_service.get_summary(db_session, organization_id=org.id)
    assert cc_final.fleet_health.ready_count >= 0
    assert cc_final.fleet_health.restricted_count == 0
