"""Milestone M21: Idempotent Demo Environment Seeder.

Populates the dedicated demo tenant ('Kota Aerospace Demo Operations') with realistic,
interconnected multi-asset sample data (drones, fixed-wing, rotorcraft, eVTOL),
telemetry events, HUMS feature baselines and exceedances, M7 proactive signals,
H8.4 MRO intelligence candidates, H8.7 human-authorized predictive maintenance,
and compliance records across operational scenarios A through F.

Usage:
    python backend/scripts/seed_m21_demo_environment.py [--reset]
"""

from __future__ import annotations

import argparse
import datetime
from datetime import UTC, timedelta
import hashlib
import json
import os
import sys
import uuid

from sqlalchemy import create_engine, select, delete, func
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

DEMO_ORG_NAME = "Kota Aerospace Demo Operations"
DEMO_ADMIN_EMAIL = "demo.admin@kotaaerospace.com"
DEMO_ENGINEER_EMAIL = "demo.engineer@kotaaerospace.com"
DEMO_PILOT_EMAIL = "demo.pilot@kotaaerospace.com"
DEMO_PASSWORD = "DemoPassword2026!Kota"


def reset_demo_organization(db: Session, org_id: uuid.UUID) -> None:
    """Safely cleans up all data belonging exclusively to the demo organization."""
    print(f"[RESET] Purging demo data for organization: {org_id}")
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
    print("[RESET] Demo organization data purge complete.")


def seed_m21_demo(db: Session, reset: bool = False) -> dict[str, any]:
    """Populates the complete M21 realistic demo environment."""
    now = datetime.datetime.now(UTC)
    results = {}

    # 1. Organization
    org = db.execute(select(Organization).where(Organization.name == DEMO_ORG_NAME)).scalar_one_or_none()
    if org is None:
        org = Organization(
            name=DEMO_ORG_NAME,
            status=OrganizationStatus.ACTIVE,
            industry=OrganizationIndustry.DRONE_UAV,
            onboarding_stage=OnboardingStage.ACTIVE,
            primary_color="#10b981",
        )
        db.add(org)
        db.flush()
        print(f"[ORG] Created demo organization: {org.name} ({org.id})")
    elif reset:
        reset_demo_organization(db, org.id)

    org_id = org.id
    results["organization_id"] = str(org_id)

    # 2. Plan & Subscription & Feature Entitlements
    demo_features = [
        "drone_fleet_management", "aircraft_fleet_management", "helicopter_fleet_management",
        "evtol_fleet_management", "flight_telemetry", "hums", "digital_twin", "mro_intelligence",
        "predictive_maintenance", "work_order_management", "battery_analytics", "compliance_management"
    ]

    sub = db.execute(select(Subscription).where(Subscription.organization_id == org_id)).scalar_one_or_none()
    if sub is None:
        suite = db.execute(select(ProductSuite).where(ProductSuite.code == "AIRCRAFT")).scalar_one_or_none()
        suite_id = suite.id if suite else None
        plan = Plan(
            name="Kota Enterprise Demo Suite",
            code=f"demo-plan-{org_id.hex[:6]}",
            suite_id=suite_id,
            is_active=True,
        )
        db.add(plan)
        db.flush()
        for feat in demo_features:
            db.add(PlanFeature(plan_id=plan.id, feature_key=feat, enabled=True))
        sub = Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            suite_id=plan.suite_id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=now - timedelta(days=90),
        )
        db.add(sub)
        db.flush()

    for feat in demo_features:
        existing_ov = db.execute(
            select(TenantFeatureOverride).where(
                TenantFeatureOverride.organization_id == org_id,
                TenantFeatureOverride.feature_key == feat,
            )
        ).scalar_one_or_none()
        if existing_ov is None:
            db.add(TenantFeatureOverride(organization_id=org_id, feature_key=feat, enabled=True))
    db.flush()


    # 3. Users & Personas
    def _create_user(email: str, name: str, roles: list[str]) -> User:
        u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if u is None:
            u = User(
                organization_id=org_id,
                email=email,
                hashed_password=hash_password(DEMO_PASSWORD),
                full_name=name,
                is_active=True,
                email_verified=True,
            )
            db.add(u)
            db.flush()
            for r in roles:
                db.add(UserRole(user_id=u.id, role_name=r, organization_id=org_id))
            db.flush()
        return u

    admin_user = _create_user(DEMO_ADMIN_EMAIL, "Sarah Jenkins (Demo Ops Director)", ["ORG_ADMIN", "CAMO_MANAGER"])
    engineer_user = _create_user(DEMO_ENGINEER_EMAIL, "Marcus Vance (Lead MRO Engineer)", ["MAINTENANCE_ENGINEER"])
    pilot_user = _create_user(DEMO_PILOT_EMAIL, "Elena Rostova (Flight Operations Lead)", ["VIEWER"])

    # 4. Facility
    facility = db.execute(select(Facility).where(Facility.organization_id == org_id)).scalar_one_or_none()
    if facility is None:
        facility = Facility(
            organization_id=org_id,
            name="Kota Integrated Operations Center",
            code="KIOC-01",
            facility_type=FacilityType.HANGAR,
            status=FacilityStatus.ACTIVE,
            description="Kota Integrated Operations Center - Primary Fleet Operations Hangar",
        )
        db.add(facility)
        db.flush()

    # Check if already seeded (Idempotency gate)
    existing_asset_count = db.execute(
        select(func.count(Asset.id)).where(Asset.organization_id == org_id)
    ).scalar_one()
    if existing_asset_count >= 9 and not reset:
        print(f"[IDEMPOTENT] M21 Demo Environment already seeded with {existing_asset_count} assets. Skipping re-seed.")
        results["status"] = "SUCCESS"
        results["asset_count"] = existing_asset_count
        results["demo_admin"] = DEMO_ADMIN_EMAIL
        return results

    # 5. Multi-Asset Fleet Setup (Scenarios A through F)
    # Scenario A: Healthy Hexacopter
    drn_01 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        model="Kota HexaCargo-X6",
        serial_number="KOTA-DRN-01",
        status="ACTIVE",
    )
    # Scenario B: Degrading Motor Vibration Drone
    drn_02 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        model="Kota SurveyPro-Q4",
        serial_number="KOTA-DRN-02",
        status="ACTIVE",
    )
    # Scenario C: Drone sharing vibration cluster
    drn_03 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        model="Kota SurveyPro-Q4",
        serial_number="KOTA-DRN-03",
        status="ACTIVE",
    )
    # Scenario E: Stale Telemetry Drone
    drn_04 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        model="Kota MediFly-V2",
        serial_number="KOTA-DRN-04",
        status="ACTIVE",
    )
    # Scenario F: Critical Anomaly Drone
    drn_05 = Asset(
        organization_id=org_id,
        asset_type=AssetType.DRONE,
        model="Kota PatrolSentinel-8",
        serial_number="KOTA-DRN-05",
        status="MAINTENANCE",
    )
    # Fixed-Wing
    fw_01 = Asset(
        organization_id=org_id,
        asset_type=AssetType.AIRCRAFT,
        model="Cessna 208B Grand Caravan",
        serial_number="N701KA",
        status="ACTIVE",
    )
    # Scenario D: Maintenance Conflict Fixed-Wing
    fw_02 = Asset(
        organization_id=org_id,
        asset_type=AssetType.AIRCRAFT,
        model="Beechcraft King Air 350",
        serial_number="N702KA",
        status="RESTRICTED",
    )
    # Rotorcraft
    hel_01 = Asset(
        organization_id=org_id,
        asset_type=AssetType.HELICOPTER,
        model="Bell 407GXi",
        serial_number="N901KA",
        status="ACTIVE",
    )
    # eVTOL
    evtol_01 = Asset(
        organization_id=org_id,
        asset_type=AssetType.EVTOL,
        model="Kota AeroShuttle eVTOL-6",
        serial_number="EV-01KA",
        status="STANDBY",
    )

    db.add_all([drn_01, drn_02, drn_03, drn_04, drn_05, fw_01, fw_02, hel_01, evtol_01])
    db.flush()

    # Link aircraft records for fixed-wing
    ac_01 = Aircraft(
        organization_id=org_id,
        asset_id=fw_01.id,
        registration="N701KA",
        msn="208B-5012",
        aircraft_type="Cessna 208B Grand Caravan",
        status="ACTIVE",
    )
    ac_02 = Aircraft(
        organization_id=org_id,
        asset_id=fw_02.id,
        registration="N702KA",
        msn="FL-982",
        aircraft_type="Beechcraft King Air 350",
        status="ACTIVE",
    )
    db.add_all([ac_01, ac_02])
    db.flush()

    # 6. Components
    c_motor_02 = Component(
        organization_id=org_id,
        asset_id=drn_02.id,
        name="Front-Right Brushless Motor",
        serial_number="MTR-DRN02-FR",
        model="KOTA-MTR-800KV",
        component_type=ComponentType.MOTOR,
        status=ComponentStatus.INSTALLED,
    )
    c_motor_03 = Component(
        organization_id=org_id,
        asset_id=drn_03.id,
        name="Front-Right Brushless Motor",
        serial_number="MTR-DRN03-FR",
        model="KOTA-MTR-800KV",
        component_type=ComponentType.MOTOR,
        status=ComponentStatus.INSTALLED,
    )
    c_rotor_hel = Component(
        organization_id=org_id,
        asset_id=hel_01.id,
        name="Main Rotor Mast & Swashplate",
        serial_number="ROTOR-407-882",
        model="BELL-407-SWP",
        component_type=ComponentType.ROTOR,
        status=ComponentStatus.INSTALLED,
    )
    db.add_all([c_motor_02, c_motor_03, c_rotor_hel])
    db.flush()

    # 7. Missions and Flights
    m1 = Mission(
        organization_id=org_id,
        asset_id=drn_01.id,
        purpose="Automated Solar Farm Thermal Inspection",
        operating_area="Area North Sector-4",
        status=MissionStatus.COMPLETED,
        planned_start=now - timedelta(hours=4),
        planned_end=now - timedelta(hours=3),
    )
    m2 = Mission(
        organization_id=org_id,
        asset_id=drn_02.id,
        purpose="Coastal Perimeter Surveillance",
        operating_area="Coastline Grid Bravo",
        status=MissionStatus.COMPLETED,
        planned_start=now - timedelta(hours=6),
        planned_end=now - timedelta(hours=5),
    )
    db.add_all([m1, m2])
    db.flush()

    # 8. Telemetry Events (Scenario A/B/C fresh vs Scenario E stale)
    # Fresh telemetry for drn_01, drn_02, drn_03, drn_05
    for asset in [drn_01, drn_02, drn_03, drn_05, fw_01, hel_01, evtol_01]:
        payload_data = {"lat": 12.9716, "lon": 77.5946, "alt": 120.0, "vibration_rms": 0.45, "battery_pct": 92}
        payload_str = json.dumps(payload_data)
        event = TelemetryEventLog(
            organization_id=org_id,
            asset_id=asset.id,
            source_system="KOTA_GATEWAY",
            source_event_id=f"EVT-{asset.serial_number}-{now.timestamp()}",
            idempotency_key=f"IDEMP-{asset.id}-{now.strftime('%Y%m%d%H%M')}",
            event_type="MAVLINK_SYS_STATUS",
            payload_hash=hashlib.sha256(payload_str.encode()).hexdigest(),
            processing_status=TelemetryProcessingStatus.PROCESSED,
            received_timestamp=now - timedelta(minutes=5),
            event_timestamp=now - timedelta(minutes=5),
        )
        db.add(event)

    # Scenario E: Stale telemetry for drn_04 (last seen 35 days ago)
    stale_time = now - timedelta(days=35)
    stale_evt = TelemetryEventLog(
        organization_id=org_id,
        asset_id=drn_04.id,
        source_system="KOTA_GATEWAY",
        source_event_id=f"EVT-STALE-{drn_04.serial_number}",
        idempotency_key=f"IDEMP-STALE-{drn_04.id}",
        event_type="MAVLINK_HEARTBEAT",
        payload_hash=hashlib.sha256(b"stale_heartbeat").hexdigest(),
        processing_status=TelemetryProcessingStatus.PROCESSED,
        received_timestamp=stale_time,
        event_timestamp=stale_time,
    )
    db.add(stale_evt)
    db.flush()

    # 9. HUMS Sensors & Exceedances (Scenarios B, C, F)
    # Motor vibration sensor for drn_02
    sensor_02 = HUMSSensor(
        organization_id=org_id,
        asset_id=drn_02.id,
        component_id=c_motor_02.id,
        sensor_code=f"SENS-VIB-02",
        sensor_type="ACCELEROMETER",
        measurement_type="VIBRATION_RMS",
        unit="g",
        warning_threshold=1.8,
        critical_threshold=3.5,
        installation_location="Motor Mount Front-Right",
        status="ACTIVE",
        source="SIMULATED",
    )
    # Motor vibration sensor for drn_03
    sensor_03 = HUMSSensor(
        organization_id=org_id,
        asset_id=drn_03.id,
        component_id=c_motor_03.id,
        sensor_code=f"SENS-VIB-03",
        sensor_type="ACCELEROMETER",
        measurement_type="VIBRATION_RMS",
        unit="g",
        warning_threshold=1.8,
        critical_threshold=3.5,
        installation_location="Motor Mount Front-Right",
        status="ACTIVE",
        source="SIMULATED",
    )
    # Bearing thermocouple sensor for drn_05
    sensor_05 = HUMSSensor(
        organization_id=org_id,
        asset_id=drn_05.id,
        sensor_code=f"SENS-TEMP-05",
        sensor_type="THERMOCOUPLE",
        measurement_type="TEMPERATURE",
        unit="CELSIUS",
        warning_threshold=75.0,
        critical_threshold=85.0,
        installation_location="Motor Bearing Chamber",
        status="ACTIVE",
        source="SIMULATED",
    )
    db.add_all([sensor_02, sensor_03, sensor_05])
    db.flush()

    # Exceedance for drn_02 (Scenario B)
    exc_02 = HUMSExceedance(
        organization_id=org_id,
        asset_id=drn_02.id,
        component_id=c_motor_02.id,
        sensor_id=sensor_02.id,
        parameter="vibration_rms",
        threshold_value=1.8,
        observed_value=3.4,
        severity="WARNING",
        window_start=now - timedelta(hours=2),
        window_end=now - timedelta(hours=1),
        contributing_reading_ids=[],
    )
    # Exceedance for drn_03 (Scenario C - correlated pattern)
    exc_03 = HUMSExceedance(
        organization_id=org_id,
        asset_id=drn_03.id,
        component_id=c_motor_03.id,
        sensor_id=sensor_03.id,
        parameter="vibration_rms",
        threshold_value=1.8,
        observed_value=3.2,
        severity="WARNING",
        window_start=now - timedelta(hours=3),
        window_end=now - timedelta(hours=2),
        contributing_reading_ids=[],
    )
    # Critical Exceedance for drn_05 (Scenario F)
    exc_05 = HUMSExceedance(
        organization_id=org_id,
        asset_id=drn_05.id,
        sensor_id=sensor_05.id,
        parameter="bearing_temperature_celsius",
        threshold_value=85.0,
        observed_value=108.5,
        severity="CRITICAL",
        window_start=now - timedelta(minutes=45),
        window_end=now - timedelta(minutes=15),
        contributing_reading_ids=[],
    )
    db.add_all([exc_02, exc_03, exc_05])
    db.flush()

    # 10. Canonical M7 Proactive Signals
    sig_crit = ProactiveSignalRecord(
        organization_id=org_id,
        asset_id=drn_05.id,
        signal_key=f"sig-crit-bearing-{drn_05.id}",
        signal_type="TEMPERATURE_SPIKE",
        severity="CRITICAL",
        priority="HIGH",
        status="OPEN",
        title="Bearing Thermal Exceedance",
        headline="Bearing temperature exceedance above maximum thermal threshold (108.5°C)",
        detected_at=now - timedelta(minutes=45),
        explanation_json=["Bearing temperature exceeded critical threshold of 85.0C during active flight."],
    )
    sig_warn_02 = ProactiveSignalRecord(
        organization_id=org_id,
        asset_id=drn_02.id,
        component_id=c_motor_02.id,
        signal_key=f"sig-warn-vib-{drn_02.id}",
        signal_type="VIBRATION_HARMONIC_ANOMALY",
        severity="WARNING",
        priority="HIGH",
        status="OPEN",
        title="Elevated Motor Vibration",
        headline="Motor bearing 2X RPM harmonic spike observed during cruise phase",
        detected_at=now - timedelta(hours=2),
        explanation_json=["Motor vibration RMS at 3.4g exceeded 1.8g warning threshold."],
    )
    sig_warn_03 = ProactiveSignalRecord(
        organization_id=org_id,
        asset_id=drn_03.id,
        component_id=c_motor_03.id,
        signal_key=f"sig-warn-vib-{drn_03.id}",
        signal_type="VIBRATION_HARMONIC_ANOMALY",
        severity="WARNING",
        priority="HIGH",
        status="OPEN",
        title="Elevated Motor Vibration",
        headline="Motor bearing 2X RPM harmonic elevated over 3 consecutive flights",
        detected_at=now - timedelta(hours=3),
        explanation_json=["Motor vibration RMS at 3.2g exceeded 1.8g warning threshold."],
    )
    db.add_all([sig_crit, sig_warn_02, sig_warn_03])
    db.flush()

    # 11. MRO Intelligence Candidates (H8.4 / H8.7)
    # Scenario B candidate: Open for review
    cand_02 = MaintenanceIntelligenceCandidate(
        organization_id=org_id,
        asset_id=drn_02.id,
        component_id=c_motor_02.id,
        candidate_type=MROCandidateType.MAINTENANCE_ATTENTION,
        status=MROCandidateStatus.OPEN,
        priority=MROCandidatePriority.HIGH,
        confidence=0.86,
        reason="Elevated motor vibration harmonics indicate premature bearing spalling",
        dedup_key=f"dedup-{drn_02.id}-{c_motor_02.id}-vib",
        source_lineage=[
            {"source_type": "HUMSExceedance", "source_id": str(exc_02.id), "label": "Vibration Exceedance 3.4g"},
            {"source_type": "ProactiveSignalRecord", "source_id": str(sig_warn_02.id), "label": "M7 Vibration Harmonic"},
        ],
        operational_impact="RESTRICTED_OPERATION",
        data_freshness="FRESH",
    )
    # Scenario D candidate: Maintenance conflict candidate
    cand_fw = MaintenanceIntelligenceCandidate(
        organization_id=org_id,
        asset_id=fw_02.id,
        candidate_type=MROCandidateType.CONFLICT_REVIEW,
        status=MROCandidateStatus.UNDER_REVIEW,
        priority=MROCandidatePriority.MEDIUM,
        confidence=0.91,
        reason="Scheduled 200-hour avionics inspection due within 4.5 flight hours during active deployment schedule",
        dedup_key=f"dedup-{fw_02.id}-sched-conflict",
        source_lineage=[{"source_type": "ComplianceObligation", "label": "Avionics Recurrent Check"}],
        operational_impact="RESTRICTED_OPERATION",
        data_freshness="FRESH",
    )
    # Scenario F candidate: Converted into drafted Work Order (H8.7)
    cand_05 = MaintenanceIntelligenceCandidate(
        organization_id=org_id,
        asset_id=drn_05.id,
        candidate_type=MROCandidateType.MAINTENANCE_ATTENTION,
        status=MROCandidateStatus.RESOLVED,
        priority=MROCandidatePriority.HIGH,
        confidence=0.95,
        reason="Bearing thermal runaway risk requires immediate motor replacement",
        dedup_key=f"dedup-{drn_05.id}-bearing-therm",
        source_lineage=[{"source_type": "HUMSExceedance", "source_id": str(exc_05.id), "label": "Thermal 108.5C"}],
        operational_impact="AOG_IMMINENT",
        data_freshness="FRESH",
        resolved_at=now - timedelta(minutes=10),
        resolved_by=admin_user.id,
        review_notes="Authorized by Operations Director. Converted to Work Order WO-PM-CRIT05",
    )
    db.add_all([cand_02, cand_fw, cand_05])
    db.flush()

    # 12. Work Orders (Developer 1 contract)
    wo_converted = WorkOrder(
        organization_id=org_id,
        asset_id=drn_05.id,
        work_order_number="WO-PM-CRIT05",
        title="Urgent: Motor Assembly Replacement (Thermal Anomaly)",
        description=(
            "Predictive Maintenance Work Order generated from Candidate {cand_05.id}.\n"
            "Source: Bearing temperature 108.5°C exceedance."
        ),
        work_order_type=WorkOrderType.CORRECTIVE,
        status=WorkOrderStatus.DRAFT,
        priority="CRITICAL",
        due_at=now + timedelta(days=2),
        source_type="PREDICTIVE_INTELLIGENCE",
        source_reference=str(cand_05.id),
        created_by_user_id=admin_user.id,
    )
    wo_routine = WorkOrder(
        organization_id=org_id,
        asset_id=fw_01.id,
        aircraft_id=ac_01.id,
        work_order_number="WO-SCHED-0102",
        title="Routine 100-Hour Airframe & Powerplant Inspection",
        description="Standard scheduled airworthiness maintenance per manufacturer service interval.",
        work_order_type=WorkOrderType.SCHEDULED,
        status=WorkOrderStatus.OPEN,
        priority="NORMAL",
        due_at=now + timedelta(days=10),
        source_type="MAINTENANCE_SCHEDULE",
        created_by_user_id=engineer_user.id,
    )
    db.add_all([wo_converted, wo_routine])
    db.flush()

    # 13. Compliance Obligations
    req = db.execute(select(RegulatoryRequirement).where(RegulatoryRequirement.requirement_number == "FAA-107-MAINT")).scalar_one_or_none()
    if req is None:
        req = RegulatoryRequirement(
            organization_id=org_id,
            requirement_number="FAA-107-MAINT",
            title="FAA Part 107 Small UAS Maintenance & Inspection Standards",
            authority=RegulatoryAuthority.FAA,
            description="Pre-flight checks and periodic structural/propulsion inspection logs.",
        )
        db.add(req)
        db.flush()

    ob1 = ComplianceObligation(
        organization_id=org_id,
        asset_id=drn_01.id,
        requirement_id=req.id,
        status=ComplianceState.COMPLIANT.value,
    )
    ob2 = ComplianceObligation(
        organization_id=org_id,
        asset_id=drn_05.id,
        requirement_id=req.id,
        status=ComplianceState.NON_COMPLIANT.value,
    )
    db.add_all([ob1, ob2])
    db.commit()

    print("[COMPLETE] Successfully seeded M21 Master Demo Environment!")
    print(f"  - Tenant: {DEMO_ORG_NAME} (ID: {org_id})")
    print(f"  - Admin Login: {DEMO_ADMIN_EMAIL} / {DEMO_PASSWORD}")
    print("  - Assets: 5 Drones, 2 Fixed-Wing, 1 Helicopter, 1 eVTOL")
    print("  - Scenarios: A (Healthy), B (Degrading), C (Correlated), D (Conflict), E (Stale), F (Critical)")

    results["status"] = "SUCCESS"
    results["asset_count"] = 9
    results["demo_admin"] = DEMO_ADMIN_EMAIL
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Kota Aerospace M21 Demo Environment")
    parser.add_argument("--reset", action="store_true", help="Reset existing demo tenant data before seeding")
    args = parser.parse_args()

    port = os.environ.get("TEST_DB_PORT", "55432")
    default_url = f"postgresql+psycopg://aerocomply:aerocomply@localhost:{port}/aerocomply_test"
    db_url = os.environ.get("DATABASE_URL", default_url)

    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    with SessionLocal() as db:
        seed_m21_demo(db, reset=args.reset)


if __name__ == "__main__":
    main()
