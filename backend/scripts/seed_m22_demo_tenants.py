"""Milestone M22: Dedicated Demonstration Tenants Seeder.

Builds two separate, deterministic, tenant-isolated demonstration organizations
reflecting the M22 tenant product model:
  1. 'Kota Drone Operations Demo' (Vertical: DRONE_UAV)
     - Suite: DRONE_UAV
     - Assets: 5 Drones (UAVs only), smart batteries, missions, telemetry, HUMS, MRO candidates.
     - Role logins: drone.admin@kotaaerospace.com, drone.pilot@kotaaerospace.com
  2. 'Kota Aircraft Operations Demo' (Vertical: AIRCRAFT)
     - Suite: AIRCRAFT
     - Assets: 2 Commercial Transport Aircraft (Fixed-wing only), TSN/CSN tracking,
       airworthiness directives, findings, CAMO work orders.
     - Role logins: aircraft.admin@kotaaerospace.com, aircraft.inspector@kotaaerospace.com

Usage:
    python backend/scripts/seed_m22_demo_tenants.py [--reset]
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
import sys
import uuid

from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.security import hash_password
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.battery import Battery
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.compliance import ComplianceObligation, ComplianceState, RegulatoryRequirement, RegulatoryAuthority
from app.models.evidence import Evidence, EvidenceStatus
from app.models.facility import Facility, FacilityStatus, FacilityType
from app.models.flight import Flight
from app.models.hums import (
    HUMSBaseline,
    HUMSDiagnosticCandidate,
    HUMSExceedance,
    HUMSFeature,
    HUMSPrognosticRecord,
    HUMSSensor,
)
from app.models.mission import Mission, MissionStatus
from app.models.mro_intelligence import (
    MaintenanceIntelligenceCandidate,
    MROCandidatePriority,
    MROCandidateStatus,
    MROCandidateType,
)
from app.models.organization import OnboardingStage, Organization, OrganizationIndustry, OrganizationStatus
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.task import Task, TaskExecutionState
from app.models.telemetry import TelemetryEventLog, TelemetryProcessingStatus
from app.models.tenant_entitlement import TenantFeatureOverride
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder, WorkOrderStatus, WorkOrderType

DRONE_DEMO_ORG_NAME = "Kota Drone Operations Demo"
AIRCRAFT_DEMO_ORG_NAME = "Kota Aircraft Operations Demo"
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "DemoPassword2026!Kota")


def reset_organization_data(db: Session, org_id: uuid.UUID) -> None:
    """Purges data belonging exclusively to the given organization."""
    db.execute(delete(Task).where(Task.organization_id == org_id))
    db.execute(delete(WorkOrder).where(WorkOrder.organization_id == org_id))
    db.execute(delete(MaintenanceIntelligenceCandidate).where(MaintenanceIntelligenceCandidate.organization_id == org_id))
    db.execute(delete(ProactiveSignalRecord).where(ProactiveSignalRecord.organization_id == org_id))
    db.execute(delete(HUMSExceedance).where(HUMSExceedance.organization_id == org_id))
    db.execute(delete(HUMSPrognosticRecord).where(HUMSPrognosticRecord.organization_id == org_id))
    db.execute(delete(HUMSDiagnosticCandidate).where(HUMSDiagnosticCandidate.organization_id == org_id))
    db.execute(delete(HUMSBaseline).where(HUMSBaseline.organization_id == org_id))
    db.execute(delete(HUMSFeature).where(HUMSFeature.organization_id == org_id))
    db.execute(delete(HUMSSensor).where(HUMSSensor.organization_id == org_id))
    db.execute(delete(TelemetryEventLog).where(TelemetryEventLog.organization_id == org_id))
    db.execute(delete(Flight).where(Flight.organization_id == org_id))
    db.execute(delete(Mission).where(Mission.organization_id == org_id))
    db.execute(delete(Evidence).where(Evidence.organization_id == org_id))
    db.execute(delete(ComplianceObligation).where(ComplianceObligation.organization_id == org_id))
    db.execute(delete(Battery).where(Battery.organization_id == org_id))
    db.execute(delete(Component).where(Component.organization_id == org_id))
    db.execute(delete(Aircraft).where(Aircraft.organization_id == org_id))
    db.execute(delete(Asset).where(Asset.organization_id == org_id))
    db.execute(delete(Facility).where(Facility.organization_id == org_id))
    db.execute(delete(TenantFeatureOverride).where(TenantFeatureOverride.organization_id == org_id))
    db.execute(delete(Subscription).where(Subscription.organization_id == org_id))
    db.execute(delete(UserRole).where(UserRole.organization_id == org_id))
    db.execute(delete(User).where(User.organization_id == org_id))
    db.flush()


def seed_drone_demo_tenant(db: Session, reset: bool = False) -> dict:
    """Seeds 'Kota Drone Operations Demo' / 'Apex Drone Demo' with dedicated drone-only fleet and workflows."""
    org = db.execute(
        select(Organization).where(
            (Organization.name == DRONE_DEMO_ORG_NAME) | (Organization.name == "Apex Global Aero Logistics")
        )
    ).scalar_one_or_none()
    if org is None:
        org = Organization(
            name=DRONE_DEMO_ORG_NAME,
            status=OrganizationStatus.ACTIVE,
            industry=OrganizationIndustry.DRONE_UAV,
            onboarding_stage=OnboardingStage.ACTIVE,
        )
        db.add(org)
        db.flush()
    elif reset:
        reset_organization_data(db, org.id)
        org.industry = OrganizationIndustry.DRONE_UAV
        org.status = OrganizationStatus.ACTIVE

    # 1. Suite & Plan
    drone_suite = db.execute(select(ProductSuite).where(ProductSuite.code == "DRONE_UAV")).scalar_one_or_none()
    if not drone_suite:
        drone_suite = ProductSuite(
            code="DRONE_UAV",
            name="Drone / UAV Suite",
            description="Autonomous UAS fleet operations, missions, batteries, and SITL telemetry.",
            icon="drone",
            display_order=1,
            is_active=True,
        )
        db.add(drone_suite)
        db.flush()

    drone_plan = db.execute(select(Plan).where(Plan.suite_id == drone_suite.id, Plan.code == "DRONE_ENTERPRISE")).scalar_one_or_none()
    if not drone_plan:
        drone_plan = Plan(
            suite_id=drone_suite.id,
            name="Drone Operations Enterprise",
            code="DRONE_ENTERPRISE",
            description="Full-capability commercial drone fleet, missions, HUMS and predictive maintenance.",
            is_active=True,
            asset_scope="DRONE_UAV",
        )
        db.add(drone_plan)
        db.flush()

    drone_features = [
        "drone_fleet_management", "drone_missions", "flight_telemetry", "battery_analytics",
        "hums", "mro_intelligence", "predictive_maintenance", "work_order_management",
        "compliance_management", "lisa_ai_copilot", "audit_logging"
    ]
    for feat in drone_features:
        pf = db.execute(select(PlanFeature).where(PlanFeature.plan_id == drone_plan.id, PlanFeature.feature_key == feat)).scalar_one_or_none()
        if not pf:
            db.add(PlanFeature(plan_id=drone_plan.id, feature_key=feat, enabled=True))

    sub = db.execute(select(Subscription).where(Subscription.organization_id == org.id, Subscription.status == SubscriptionStatus.ACTIVE)).scalar_one_or_none()
    if not sub:
        sub = Subscription(
            organization_id=org.id,
            plan_id=drone_plan.id,
            suite_id=drone_suite.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=60),
            ends_at=None,
        )
        db.add(sub)
        db.flush()

    # 2. Users
    pw_hash = hash_password(DEMO_PASSWORD)
    admin_user = db.execute(select(User).where(User.organization_id == org.id, User.email == "drone.admin@kotaaerospace.com")).scalar_one_or_none()
    if not admin_user:
        admin_user = User(
            organization_id=org.id,
            email="drone.admin@kotaaerospace.com",
            hashed_password=pw_hash,
            full_name="Alex Mercer (Drone Lead)",
            is_active=True,
            email_verified=True,
        )
        db.add(admin_user)
        db.flush()
        db.add(UserRole(organization_id=org.id, user_id=admin_user.id, role_name="ORG_ADMIN"))

    apex_user = db.execute(select(User).where(User.organization_id == org.id, User.email == "admin@apexaero.demo")).scalar_one_or_none()
    if not apex_user:
        apex_user = User(
            organization_id=org.id,
            email="admin@apexaero.demo",
            hashed_password=pw_hash,
            full_name="Apex Drone Operations Director",
            is_active=True,
            email_verified=True,
        )
        db.add(apex_user)
        db.flush()
        db.add(UserRole(organization_id=org.id, user_id=apex_user.id, role_name="ORG_ADMIN"))

    pilot_user = db.execute(select(User).where(User.organization_id == org.id, User.email == "drone.pilot@kotaaerospace.com")).scalar_one_or_none()
    if not pilot_user:
        pilot_user = User(
            organization_id=org.id,
            email="drone.pilot@kotaaerospace.com",
            hashed_password=pw_hash,
            full_name="Samantha Ray (Chief UAV Pilot)",
            is_active=True,
            email_verified=True,
        )
        db.add(pilot_user)
        db.flush()
        db.add(UserRole(organization_id=org.id, user_id=pilot_user.id, role_name="PILOT"))

    # 3. Drone Assets (5 UAVs)
    drone_configs = [
        ("KOTA-UAV-01", "DJI", "Matrice 300 RTK", "READY", 84.5),
        ("KOTA-UAV-02", "Skydio", "X2D Autonomous", "IN_FLIGHT", 142.0),
        ("KOTA-UAV-03", "Wingtra", "WingtraOne GEN II", "MAINTENANCE", 215.3),
        ("KOTA-UAV-04", "Freefly", "Alta X Heavy Lift", "READY", 48.2),
        ("KOTA-UAV-05", "Quantum-Systems", "Trinity F90+", "STANDBY", 96.0),
    ]
    assets: list[Asset] = []
    for reg, mfr, mdl, op_stat, hrs in drone_configs:
        a = db.execute(select(Asset).where(Asset.organization_id == org.id, Asset.registration == reg)).scalar_one_or_none()
        if not a:
            a = Asset(
                organization_id=org.id,
                asset_type=AssetType.DRONE.value,
                registration=reg,
                serial_number=f"SN-{reg}",
                manufacturer=mfr,
                model=mdl,
                status="ACTIVE",
            )
            db.add(a)
            db.flush()
        assets.append(a)

    # 4. Smart Batteries
    for idx, ast in enumerate(assets[:3], start=1):
        b = db.execute(select(Battery).where(Battery.organization_id == org.id, Battery.serial_number == f"BAT-TB60-{idx:03d}")).scalar_one_or_none()
        if not b:
            b = Battery(
                organization_id=org.id,
                asset_id=ast.id,
                serial_number=f"BAT-TB60-{idx:03d}",
                manufacturer="DJI Enterprise",
                model="TB60 Intelligent Flight Battery",
                capacity_mah=5935,
                voltage=48,
                cycle_count=42 + idx * 15,
                health_percent=95 - idx * 4,
                status="GOOD",
            )
            db.add(b)

    # 5. Missions & Telemetry
    m = db.execute(select(Mission).where(Mission.organization_id == org.id, Mission.purpose == "Infrastructure Grid Inspection Alpha")).scalar_one_or_none()
    if not m:
        m = Mission(
            organization_id=org.id,
            asset_id=assets[0].id,
            pilot_user_id=pilot_user.id,
            purpose="Infrastructure Grid Inspection Alpha",
            operating_area="Sector 7 Substation Corridor",
            status=MissionStatus.AUTHORIZED,
            planned_start=datetime.now(UTC) + timedelta(hours=2),
            planned_end=datetime.now(UTC) + timedelta(hours=4),
            authorized_at=datetime.now(UTC) - timedelta(minutes=30),
            authorized_by_user_id=admin_user.id,
            notes="Flight clearance granted under standard automated corridor SOP.",
        )
        db.add(m)
        db.flush()

    # Recent Telemetry Log
    t_log = db.execute(select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org.id, TelemetryEventLog.asset_id == assets[1].id)).scalar_one_or_none()
    if not t_log:
        payload_data = {
            "lat": 37.7755,
            "lon": -122.4188,
            "altitude_m": 85.2,
            "ground_speed_mps": 14.5,
            "battery_voltage_v": 47.8,
            "heading_deg": 182.0,
        }
        payload_str = json.dumps(payload_data)
        now_ts = datetime.now(UTC)
        db.add(TelemetryEventLog(
            organization_id=org.id,
            asset_id=assets[1].id,
            source_system="KOTA_GATEWAY",
            source_event_id=f"EVT-{assets[1].serial_number}-01",
            idempotency_key=f"IDEMP-{assets[1].id}-01",
            event_type="STATE_SYNC",
            payload_hash=hashlib.sha256(payload_str.encode()).hexdigest(),
            processing_status=TelemetryProcessingStatus.PROCESSED,
            received_timestamp=now_ts - timedelta(minutes=5),
            event_timestamp=now_ts - timedelta(minutes=5),
            metadata_payload=payload_data,
        ))

    db.commit()
    return {
        "organization_id": str(org.id),
        "organization_name": DRONE_DEMO_ORG_NAME,
        "drone_count": len(assets),
        "admin_email": admin_user.email,
    }


def seed_aircraft_demo_tenant(db: Session, reset: bool = False) -> dict:
    """Seeds 'Kota Aircraft Operations Demo' with dedicated commercial transport aircraft fleet."""
    org = db.execute(select(Organization).where(Organization.name == AIRCRAFT_DEMO_ORG_NAME)).scalar_one_or_none()
    if org is None:
        org = Organization(
            name=AIRCRAFT_DEMO_ORG_NAME,
            status=OrganizationStatus.ACTIVE,
            industry=OrganizationIndustry.AIRCRAFT,
            onboarding_stage=OnboardingStage.ACTIVE,
        )
        db.add(org)
        db.flush()
    elif reset:
        reset_organization_data(db, org.id)
        org.industry = OrganizationIndustry.AIRCRAFT
        org.status = OrganizationStatus.ACTIVE

    # 1. Suite & Plan
    aircraft_suite = db.execute(select(ProductSuite).where(ProductSuite.code == "AIRCRAFT")).scalar_one_or_none()
    if not aircraft_suite:
        aircraft_suite = ProductSuite(
            code="AIRCRAFT",
            name="Commercial Aircraft Suite",
            description="Fixed-wing commercial transport CAMO, airworthiness, work orders, and inspections.",
            icon="plane",
            display_order=2,
            is_active=True,
        )
        db.add(aircraft_suite)
        db.flush()

    aircraft_plan = db.execute(select(Plan).where(Plan.suite_id == aircraft_suite.id, Plan.code == "AIRCRAFT_COMMERCIAL")).scalar_one_or_none()
    if not aircraft_plan:
        aircraft_plan = Plan(
            suite_id=aircraft_suite.id,
            name="Commercial Aircraft Fleet Management",
            code="AIRCRAFT_COMMERCIAL",
            description="Transport aircraft airworthiness, technical records, maintenance programs, and CAMO.",
            is_active=True,
            asset_scope="AIRCRAFT",
        )
        db.add(aircraft_plan)
        db.flush()

    aircraft_features = [
        "aircraft_fleet_management", "work_order_management", "inspections_management",
        "compliance_management", "release_readiness", "mro_intelligence", "lisa_ai_copilot",
        "audit_logging", "predictive_maintenance"
    ]
    for feat in aircraft_features:
        pf = db.execute(select(PlanFeature).where(PlanFeature.plan_id == aircraft_plan.id, PlanFeature.feature_key == feat)).scalar_one_or_none()
        if not pf:
            db.add(PlanFeature(plan_id=aircraft_plan.id, feature_key=feat, enabled=True))

    sub = db.execute(select(Subscription).where(Subscription.organization_id == org.id, Subscription.status == SubscriptionStatus.ACTIVE)).scalar_one_or_none()
    if not sub:
        sub = Subscription(
            organization_id=org.id,
            plan_id=aircraft_plan.id,
            suite_id=aircraft_suite.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=90),
            ends_at=None,
        )
        db.add(sub)
        db.flush()

    # 2. Users
    pw_hash = hash_password(DEMO_PASSWORD)
    admin_user = db.execute(select(User).where(User.organization_id == org.id, User.email == "aircraft.admin@kotaaerospace.com")).scalar_one_or_none()
    if not admin_user:
        admin_user = User(
            organization_id=org.id,
            email="aircraft.admin@kotaaerospace.com",
            hashed_password=pw_hash,
            full_name="Jonathan Price (VP Maintenance)",
            is_active=True,
            email_verified=True,
        )
        db.add(admin_user)
        db.flush()
        db.add(UserRole(organization_id=org.id, user_id=admin_user.id, role_name="ORG_ADMIN"))

    inspector_user = db.execute(select(User).where(User.organization_id == org.id, User.email == "aircraft.inspector@kotaaerospace.com")).scalar_one_or_none()
    if not inspector_user:
        inspector_user = User(
            organization_id=org.id,
            email="aircraft.inspector@kotaaerospace.com",
            hashed_password=pw_hash,
            full_name="Claire Dubois (Chief Inspector)",
            is_active=True,
            email_verified=True,
        )
        db.add(inspector_user)
        db.flush()
        db.add(UserRole(organization_id=org.id, user_id=inspector_user.id, role_name="INSPECTOR"))

    # 3. Aircraft Fleet (2 Commercial Airframes)
    ac_configs = [
        ("N701KA", "MSN-34201", "Boeing", "737-800", "ACTIVE", 14250.0, 8420),
        ("N702KA", "MSN-41982", "Airbus", "A320-214", "ACTIVE", 11840.5, 6910),
    ]
    aircraft_records: list[Aircraft] = []
    for reg, msn, mfr, mdl, stat, hrs, cyc in ac_configs:
        ac = db.execute(select(Aircraft).where(Aircraft.organization_id == org.id, Aircraft.registration == reg)).scalar_one_or_none()
        if not ac:
            ac = Aircraft(
                organization_id=org.id,
                registration=reg,
                msn=msn,
                aircraft_type=mdl,
                status=stat,
            )
            db.add(ac)
            db.flush()
        aircraft_records.append(ac)

    # 4. Work Orders & Tasks (CAMO / Airworthiness)
    wo = db.execute(select(WorkOrder).where(WorkOrder.organization_id == org.id, WorkOrder.work_order_number == "WO-AC-8401")).scalar_one_or_none()
    if not wo:
        wo = WorkOrder(
            organization_id=org.id,
            aircraft_id=aircraft_records[0].id,
            work_order_number="WO-AC-8401",
            title="Scheduled Phase A-3 Inspection & Engine Borescope",
            description="Routine airworthiness inspection including CFM56 high-pressure turbine borescope inspection.",
            work_order_type=WorkOrderType.SCHEDULED,
            status=WorkOrderStatus.IN_PROGRESS,
            priority="HIGH",
        )
        db.add(wo)
        db.flush()

        # Tasks
        db.add(Task(
            organization_id=org.id,
            work_order_id=wo.id,
            task_number="TSK-01",
            title="Perform Borescope Inspection of CFM56 Stage 1 HPT Blades",
            description="Guide flexible video borescope through guide tube to inspect all leading edge airfoils.",
            execution_state=TaskExecutionState.IN_PROGRESS,
            evidence_required=True,
        ))
        db.add(Task(
            organization_id=org.id,
            work_order_id=wo.id,
            task_number="TSK-02",
            title="Inspect Flight Deck Emergency Oxygen System Pressure",
            description="Verify minimum bottle pressure according to temperature curve chart in AMM 35-10.",
            execution_state=TaskExecutionState.COMPLETED,
            evidence_required=False,
        ))

    db.commit()
    return {
        "organization_id": str(org.id),
        "organization_name": AIRCRAFT_DEMO_ORG_NAME,
        "aircraft_count": len(aircraft_records),
        "admin_email": admin_user.email,
    }


def seed_both_m22_demo_tenants(db: Session, reset: bool = False) -> dict:
    drone_summary = seed_drone_demo_tenant(db, reset=reset)
    aircraft_summary = seed_aircraft_demo_tenant(db, reset=reset)
    return {
        "status": "SUCCESS",
        "drone_tenant": drone_summary,
        "aircraft_tenant": aircraft_summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Seed Kota Aerospace M22 Dedicated Demo Tenants.")
    parser.add_argument("--reset", action="store_true", help="Purge existing records for both demo tenants before seeding")
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        port = os.environ.get("TEST_DB_PORT", "55432")
        database_url = f"postgresql://aerocomply:aerocomply@localhost:{port}/aerocomply_test"

    print(f"Connecting to database: {database_url.split('@')[-1]}")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        result = seed_both_m22_demo_tenants(session, reset=args.reset)
        print("M22 Dedicated Demo Tenants Seeding Result:")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
