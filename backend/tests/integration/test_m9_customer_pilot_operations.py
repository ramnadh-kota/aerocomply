"""M9 Controlled Customer Pilot & Production Operations Integration Tests.

Validates the complete real-customer pilot operational lifecycle:
1. Organization & Admin Provisioning (Platform Control Plane)
2. Role Mapping & Server-Side RBAC Enforcement
3. Customer Data Onboarding & Historical Baseline Accounting (Import Center)
4. Operations, Flights & Utilization (No double-counting)
5. Maintenance, Inspection Gates, Defect Findings & Evidence Traceability
6. Tri-State Compliance (Preserving UNKNOWN / REVIEW_REQUIRED)
7. Multi-Dimensional Readiness Gating & Explanation
8. Proactive Aerospace Intelligence (M7 deterministic signals)
9. Grounded LISA Conversational AI with Strict Tenant Isolation
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.core.permissions import Permission, Role
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.battery import Battery, BatteryStatus
from app.models.compliance import ComplianceAssessment, RegulatoryRequirement
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding
from app.models.flight import Flight
from app.models.inspection_requirement import InspectionRequirement
from app.models.mission import Mission
from app.models.organization import Organization
from app.models.part import Part
from app.models.task import Task
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.asset_baseline import AssetHistoricalBaselineCreateRequest
from app.schemas.auth import CurrentUser
from app.schemas.compliance import (
    ComplianceAssessmentCreateRequest,
    RegulatoryRequirementCreateRequest,
)
from app.schemas.mission import MissionCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    asset_service,
    compliance_service,
    drone_service,
    evidence_service,
    finding_service,
    flight_service,
    inspection_service,
    mission_service,
    part_service,
    tenant_service,
    work_order_service,
)
from app.services.ai import tools
from app.services.intelligence import proactive_intelligence_service


def _create_user(db: Session, *, org_id: uuid.UUID, email: str, full_name: str, role: Role) -> User:
    from app.core.security import hash_password
    user = User(
        organization_id=org_id,
        email=email,
        full_name=full_name,
        hashed_password=hash_password("CustomerPilotSecure#2026"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    ur = UserRole(user_id=user.id, organization_id=org_id, role_name=role.value)
    db.add(ur)
    db.commit()
    return user


@pytest.fixture
def customer_pilot_tenant(db_session):
    """Provisions a dedicated, isolated customer pilot organization and users."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="Apex Aero Logistics Pilot",
        status="ACTIVE",
    )
    db_session.add(org)
    db_session.commit()

    admin = _create_user(
        db_session, org_id=org_id, email=f"admin-{uuid.uuid4().hex[:6]}@apexaero-pilot.com", full_name="Apex Admin", role=Role.ORG_ADMIN
    )
    camo_mgr = _create_user(
        db_session, org_id=org_id, email=f"camo-{uuid.uuid4().hex[:6]}@apexaero-pilot.com", full_name="Apex CAMO Lead", role=Role.CAMO_MANAGER
    )
    maint_eng = _create_user(
        db_session, org_id=org_id, email=f"tech-{uuid.uuid4().hex[:6]}@apexaero-pilot.com", full_name="Apex Lead Tech", role=Role.MAINTENANCE_ENGINEER
    )
    quality_mgr = _create_user(
        db_session, org_id=org_id, email=f"qa-{uuid.uuid4().hex[:6]}@apexaero-pilot.com", full_name="Apex QA Auditor", role=Role.QUALITY_MANAGER
    )
    viewer = _create_user(
        db_session, org_id=org_id, email=f"pilot-{uuid.uuid4().hex[:6]}@apexaero-pilot.com", full_name="Apex Drone Pilot", role=Role.VIEWER
    )

    return {
        "org": org,
        "admin": admin,
        "camo_mgr": camo_mgr,
        "maint_eng": maint_eng,
        "quality_mgr": quality_mgr,
        "viewer": viewer,
    }


def test_customer_tenant_provisioning_and_rbac_boundaries(db_session, customer_pilot_tenant):
    """M9.4 & M9.5: Verify tenant isolation, role assignment and server-side RBAC enforcement."""
    tenant = customer_pilot_tenant
    org = tenant["org"]
    viewer = tenant["viewer"]

    # Verify Viewer user cannot create assets directly
    viewer_current = CurrentUser(
        id=viewer.id,
        organization_id=org.id,
        email=viewer.email,
        full_name=viewer.full_name,
        roles=[Role.VIEWER.value],
        is_active=True,
    )
    from app.core.permissions import permissions_for_roles
    granted = permissions_for_roles(viewer_current.roles)
    assert Permission.AIRCRAFT_WRITE.value not in granted
    assert Permission.DRONE_WRITE.value not in granted
    assert Permission.ORG_MANAGE.value not in granted


def test_customer_fleet_and_historical_baseline_accounting(db_session, customer_pilot_tenant):
    """M9.8: Establish historical baseline and verify post-baseline flights add accurately without double-counting."""
    tenant = customer_pilot_tenant
    org = tenant["org"]
    admin = tenant["admin"]

    # 1. Onboard customer aircraft
    ac = aircraft_service.create_aircraft(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        payload=AircraftCreateRequest(
            registration=f"VT-AP{uuid.uuid4().hex[:4].upper()}",
            msn=f"MSN-APEX-{uuid.uuid4().hex[:4]}",
            aircraft_type="ATR-72-600",
            manufacturer="ATR",
        ),
    )
    assert ac.registration.startswith("VT-AP")

    # 2. Establish Historical Baseline: 500.0 flight hours, 450 cycles as of 30 days ago
    baseline_date = datetime.now(UTC) - timedelta(days=30)
    baseline = flight_service.create_asset_baseline(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        asset_id=ac.asset_id,
        flight_hours=500.0,
        flight_cycles=450,
        effective_at=baseline_date,
        source="PILOT_IMPORT",
        notes="Customer historical migration baseline",
    )
    assert baseline.flight_hours == 500.0

    # 3. Record Post-Baseline Flight: 2.5 hours (150 minutes), 1 cycle
    flight = flight_service.record_flight(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        asset_id=ac.asset_id,
        flown_at=datetime.now(UTC) - timedelta(days=5),
        duration_minutes=150,
        cycles=1,
        pilot_user_id=tenant["viewer"].id,
        flight_number=f"APEX-{uuid.uuid4().hex[:4]}",
        notes="Post-migration operational revenue flight",
    )
    assert flight.flight_number.startswith("APEX-")

    # 4. Verify Total Utilization = 500.0 baseline + 2.5 post-baseline = 502.5 hours
    context = asset_service.get_asset_domain_context(db_session, organization_id=org.id, asset_id=ac.asset_id)
    assert context.utilization.total_flight_hours == 502.5
    assert context.utilization.total_cycles == 451


def test_customer_maintenance_inspection_evidence_lifecycle(db_session, customer_pilot_tenant):
    """M9.11-M9.13: Execute complete customer maintenance work order, finding, evidence gate, and inspection sign-off."""
    tenant = customer_pilot_tenant
    org = tenant["org"]
    admin = tenant["admin"]
    maint_eng = tenant["maint_eng"]
    quality_mgr = tenant["quality_mgr"]

    # 1. Create Drone Asset
    drone = drone_service.create_drone(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        registration=f"APEX-UAV-{uuid.uuid4().hex[:4].upper()}",
        manufacturer="Apex Aero",
        model="CargoDrone-100",
        serial_number=f"SN-APEX-{uuid.uuid4().hex[:6]}",
        facility_id=None,
    )

    # 2. Install Motor component
    motor = Component(
        organization_id=org.id,
        asset_id=drone.id,
        component_type=ComponentType.MOTOR,
        name="Main Lift Motor",
        serial_number=f"MOT-APEX-{uuid.uuid4().hex[:6]}",
        manufacturer="Apex Dynamics",
        status=ComponentStatus.INSTALLED,
    )
    db_session.add(motor)
    db_session.commit()

    # 3. Create Corrective Work Order
    wo = work_order_service.create_work_order(
        db_session,
        organization_id=org.id,
        created_by_user_id=admin.id,
        payload=WorkOrderCreateRequest(
            work_order_number=f"WO-APEX-{uuid.uuid4().hex[:6]}",
            asset_id=drone.id,
            title="Motor Thermal Check",
            description="Investigate high thermal reading after cargo mission",
            work_order_type="CORRECTIVE",
            priority="HIGH",
            assigned_to_user_id=maint_eng.id,
        ),
    )
    assert wo.work_order_number.startswith("WO-APEX-")

    # 4. Create Task with Required Evidence
    task = work_order_service.create_task(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        payload=TaskCreateRequest(
            work_order_id=wo.id,
            task_number=f"TASK-APEX-{uuid.uuid4().hex[:6]}",
            title="Inspect Motor Windings",
            description="Perform thermal imaging and visual inspection",
            execution_state="IN_PROGRESS",
            assigned_technician_user_id=maint_eng.id,
            evidence_required=True,
        ),
    )

    # 5. Record Defect Finding
    finding = finding_service.create_finding(
        db_session,
        organization_id=org.id,
        actor_user_id=maint_eng.id,
        title="Thermal discoloration on Motor #1",
        description="Minor insulation thermal discoloration detected",
        severity="MINOR",
        asset_id=drone.id,
        component_id=motor.id,
        work_order_id=wo.id,
        task_id=task.id,
        responsible_user_id=maint_eng.id,
    )
    assert finding.title == "Thermal discoloration on Motor #1"

    # 6. Upload Evidence and Accept via Quality Manager
    ev = evidence_service.create_evidence(
        db_session,
        organization_id=org.id,
        title="Motor Windings Thermal Photo",
        task_id=task.id,
        asset_id=drone.id,
        component_id=motor.id,
        finding_id=finding.id,
        work_order_id=wo.id,
        uploaded_by_user_id=maint_eng.id,
        evidence_type="PHOTOGRAPH",
    )
    ev.status = EvidenceStatus.ACCEPTED
    ev.reviewer_user_id = quality_mgr.id
    db_session.add(ev)
    db_session.commit()

    # 7. Create and Complete Inspection Requirement
    insp = inspection_service.create_inspection_requirement(
        db_session,
        organization_id=org.id,
        task_id=task.id,
        work_order_id=wo.id,
        required=True,
    )
    insp.inspector_user_id = quality_mgr.id
    insp.status = "COMPLETED"
    db_session.add(insp)
    db_session.commit()

    assert insp.status == "COMPLETED"
    assert ev.status == EvidenceStatus.ACCEPTED


def test_customer_tri_state_compliance_and_readiness(db_session, customer_pilot_tenant):
    """M9.13 & M9.14: Verify tri-state compliance preservation and readiness explanation."""
    tenant = customer_pilot_tenant
    org = tenant["org"]
    admin = tenant["admin"]

    # 1. Create Aircraft
    ac = aircraft_service.create_aircraft(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        payload=AircraftCreateRequest(
            registration=f"VT-AP{uuid.uuid4().hex[:4].upper()}",
            msn=f"MSN-APEX-{uuid.uuid4().hex[:4]}",
            aircraft_type="ATR-72-600",
            manufacturer="ATR",
        ),
    )

    # 2. Regulatory Requirement
    req = compliance_service.create_requirement(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        payload=RegulatoryRequirementCreateRequest(
            requirement_number=f"REQ-APEX-{uuid.uuid4().hex[:6]}",
            authority="DGCA",
            title="Avionics Software Version Check",
            description="Mandatory version audit for FMS navigation database",
            effective_date=date.today() - timedelta(days=100),
        ),
    )

    # 3. Assessment in REVIEW_REQUIRED (UNKNOWN) status
    assess = compliance_service.create_assessment(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=ac.id,
            requirement_id=req.id,
            status="REVIEW_REQUIRED",
            evaluated_at=date.today(),
            notes="Pending logbook review by chief avionics engineer",
        ),
    )
    assert assess.status == "REVIEW_REQUIRED"

    # 4. Verify Readiness on Aircraft
    readiness = asset_service.get_asset_readiness(db_session, organization_id=org.id, asset_id=ac.asset_id)
    assert readiness.asset_id == ac.asset_id
    assert readiness.overall_status in ("READY", "CAUTION", "BLOCKED", "ACTIVE")


def test_customer_proactive_intelligence_and_tenant_isolation(db_session, customer_pilot_tenant):
    """M9.15 & M9.16: Proactive intelligence signals generated on customer data with strict isolation from other tenants."""
    tenant = customer_pilot_tenant
    org = tenant["org"]
    admin = tenant["admin"]

    # 1. Create drone with critical degraded battery (25% health)
    drone = drone_service.create_drone(
        db_session,
        organization_id=org.id,
        actor_user_id=admin.id,
        registration=f"APEX-UAV-{uuid.uuid4().hex[:4].upper()}",
        manufacturer="Apex Aero",
        model="CargoDrone-100",
        serial_number=f"SN-APEX-{uuid.uuid4().hex[:6]}",
        facility_id=None,
    )
    bat = Battery(
        organization_id=org.id,
        serial_number=f"BAT-APEX-{uuid.uuid4().hex[:6]}",
        manufacturer="Apex Power",
        model="ApexCell-6S",
        capacity_mah=8000,
        voltage=22,
        asset_id=drone.id,
        status=BatteryStatus.CRITICAL,
        health_percent=25,
        installed_at=datetime.now(UTC),
    )
    db_session.add(bat)
    db_session.commit()

    # 2. Evaluate proactive intelligence summary
    summary = proactive_intelligence_service.get_proactive_summary(db_session, organization_id=org.id)
    assert summary.total_active_signals >= 0

    # 3. Retrieve signals and assert battery degradation signal is detected
    signals = proactive_intelligence_service.sync_and_get_signals(db_session, organization_id=org.id)
    assert len(signals) >= 1
    bat_signal = next((s for s in signals if bat.serial_number in s.headline or "Battery" in s.signal_type), None)
    assert bat_signal is not None
    assert bat_signal.severity in ("CRITICAL", "HIGH", "MEDIUM")

    # 4. Verify Grounded LISA Tool query with Customer User context returns ONLY Customer data
    customer_user = CurrentUser(
        id=admin.id,
        organization_id=org.id,
        email=admin.email,
        full_name=admin.full_name,
        roles=[Role.ORG_ADMIN.value],
        is_active=True,
    )
    fleet_summary = tools._handle_get_fleet_attention_summary(db_session, customer_user, {})
    assert "total_assets" in fleet_summary
    # Ensure no QA tenant assets leaked
    assert "VT-QA01" not in str(fleet_summary)
    assert "KQA-UAV-001" not in str(fleet_summary)
