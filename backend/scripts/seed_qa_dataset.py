"""M7: deterministic, idempotent synthetic aerospace QA dataset.

Seeds a realistic, connected dataset into ONE existing tenant organization
(identified by QA_ORG_ID below, or overridden via the QA_ORG_ID env var) so
the platform can be exercised end-to-end -- asset -> flight -> finding ->
maintenance -> evidence -> inspection -> compliance -- instead of only
empty-state CRUD testing. All data created here is explicitly synthetic QA
data; every organization/user/asset name is prefixed "QA" or "KQA" so it is
never mistaken for a real customer.

Follows the same "standalone script with direct DATABASE_URL access, safe
to re-run" pattern as scripts/seed_product_catalog.py and
scripts/create_platform_admin.py -- every entity is looked up by a stable
natural key first (email, registration, serial number, etc.); if it already
exists, this script reports it and moves on without creating a duplicate.
Re-running this script is always safe and produces no new rows.

Uses this codebase's real service-layer functions wherever one exists
(app/services/*.py), not raw ORM inserts, so every seeded row passes the
same validation/audit path a real API caller would. Component and Battery
have no dedicated service-layer creator (confirmed by inspection -- this
codebase's own test suite creates them via direct ORM, e.g.
tests/integration/test_battery_component_maintenance.py), so those two are
the only raw ORM inserts here.

PRODUCTION SAFETY: refuses to run unless ENVIRONMENT is "development" or
"staging" (matches app.core.config.Settings.environment's documented
values). There is no override flag -- if you need to run this against a
different environment name, change the code deliberately, not by passing a
flag that could be set accidentally.

Usage:
    DATABASE_URL=postgresql+psycopg://... ENVIRONMENT=staging \\
        python scripts/seed_qa_dataset.py
"""

import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 -- registers every mapped class app/models/__init__.py imports
from app.models import regulatory_document  # noqa: F401 -- RegulatoryRequirement's FK target; not re-exported by app/models/__init__.py
from app.core.errors import AeroComplyError
from app.core.permissions import Role
from app.models.asset import Asset, AssetType
from app.models.battery import Battery, BatteryStatus
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.organization import Organization
from app.models.part import Part
from app.models.user import User, UserRole
from app.schemas.aircraft import AircraftCreateRequest
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

QA_ORG_ID = uuid.UUID(os.environ.get("QA_ORG_ID", "b990db30-78f4-4666-b141-ff23a1f73177"))
QA_PASSWORD = "QaStaging#2026"  # synthetic-only account; never used for a real customer


def _guard_environment() -> None:
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment not in ("development", "staging"):
        print(
            f"Refusing to run the synthetic QA seed against ENVIRONMENT={environment!r}. "
            "This script only runs against development or staging.",
            file=sys.stderr,
        )
        sys.exit(1)


def _get_or_create_user(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, email: str, full_name: str, role: str):
    existing = db.execute(
        select(User).where(User.email == email, User.organization_id == org_id)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] user {email} already exists")
        return existing
    created = tenant_service.create_tenant_user_direct(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        email=email,
        full_name=full_name,
        password=QA_PASSWORD,
        role=role,
    )
    print(f"  [created] user {email} ({role})")
    return db.get(User, created.id)


def _get_or_create_aircraft(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, registration: str, msn: str, aircraft_type: str, manufacturer: str):
    from app.models.aircraft import Aircraft

    existing = db.execute(
        select(Aircraft).where(Aircraft.organization_id == org_id, Aircraft.registration == registration)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] aircraft {registration} already exists")
        return existing
    aircraft = aircraft_service.create_aircraft(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        payload=AircraftCreateRequest(
            registration=registration, msn=msn, aircraft_type=aircraft_type, manufacturer=manufacturer
        ),
    )
    print(f"  [created] aircraft {registration} ({aircraft_type})")
    return aircraft


def _get_or_create_drone(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, registration: str, manufacturer: str, model: str, serial_number: str):
    existing = db.execute(
        select(Asset).where(
            Asset.organization_id == org_id,
            Asset.registration == registration,
            Asset.asset_type == AssetType.DRONE.value,
        )
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] drone {registration} already exists")
        return existing
    drone = drone_service.create_drone(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        registration=registration,
        manufacturer=manufacturer,
        model=model,
        serial_number=serial_number,
        facility_id=None,
    )
    print(f"  [created] drone {registration}")
    return drone


def _get_or_create_battery(db: Session, *, org_id: uuid.UUID, serial_number: str, asset_id: uuid.UUID | None, status: str, health_percent: int | None):
    existing = db.execute(
        select(Battery).where(Battery.organization_id == org_id, Battery.serial_number == serial_number)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] battery {serial_number} already exists")
        return existing
    battery = Battery(
        organization_id=org_id,
        serial_number=serial_number,
        manufacturer="KOTA Aerospace QA Cells",
        model="LiPo-6S-Q",
        capacity_mah=6000,
        voltage=22,
        asset_id=asset_id,
        status=status,
        health_percent=health_percent,
        installed_at=datetime.now(UTC) if asset_id else None,
    )
    db.add(battery)
    db.commit()
    db.refresh(battery)
    print(f"  [created] battery {serial_number} ({status})")
    return battery


def _get_or_create_component(db: Session, *, org_id: uuid.UUID, asset_id: uuid.UUID, component_type: str, name: str, serial_number: str, status: str):
    existing = db.execute(
        select(Component).where(Component.organization_id == org_id, Component.serial_number == serial_number)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] component {serial_number} already exists")
        return existing
    component = Component(
        organization_id=org_id,
        asset_id=asset_id,
        component_type=component_type,
        name=name,
        serial_number=serial_number,
        manufacturer="KOTA Aerospace QA Parts",
        status=status,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    print(f"  [created] component {serial_number} ({name})")
    return component


def _get_or_create_mission(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, asset_id: uuid.UUID, pilot_id: uuid.UUID, purpose: str, operating_area: str):
    from app.models.mission import Mission

    existing = db.execute(
        select(Mission).where(
            Mission.organization_id == org_id, Mission.asset_id == asset_id, Mission.purpose == purpose
        )
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] mission {purpose!r} for asset already exists")
        return existing
    mission = mission_service.create_mission(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        payload=MissionCreateRequest(
            asset_id=asset_id,
            pilot_user_id=pilot_id,
            purpose=purpose,
            operating_area=operating_area,
            planned_start=datetime.now(UTC) - timedelta(days=2),
            planned_end=datetime.now(UTC) - timedelta(days=2, hours=-2),
        ),
    )
    print(f"  [created] mission {purpose!r}")
    return mission


def _get_or_create_flight(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, asset_id: uuid.UUID, mission_id: uuid.UUID, pilot_id: uuid.UUID, flight_number: str, duration_minutes: int):
    from app.models.flight import Flight

    existing = db.execute(
        select(Flight).where(Flight.organization_id == org_id, Flight.flight_number == flight_number)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] flight {flight_number} already exists")
        return existing
    flight = flight_service.record_flight(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        asset_id=asset_id,
        flown_at=datetime.now(UTC) - timedelta(days=2),
        duration_minutes=duration_minutes,
        cycles=1,
        pilot_user_id=pilot_id,
        mission_id=mission_id,
        flight_number=flight_number,
        notes="Synthetic QA flight record",
    )
    print(f"  [created] flight {flight_number}")
    return flight


def _get_or_create_work_order(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, work_order_number: str, **kwargs):
    from app.models.work_order import WorkOrder

    existing = db.execute(
        select(WorkOrder).where(WorkOrder.organization_id == org_id, WorkOrder.work_order_number == work_order_number)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] work order {work_order_number} already exists")
        return existing
    work_order = work_order_service.create_work_order(
        db,
        organization_id=org_id,
        created_by_user_id=actor_id,
        payload=WorkOrderCreateRequest(work_order_number=work_order_number, **kwargs),
    )
    print(f"  [created] work order {work_order_number}")
    return work_order


def _get_or_create_task(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, work_order_id: uuid.UUID, task_number: str, **kwargs):
    from app.models.task import Task

    existing = db.execute(
        select(Task).where(Task.organization_id == org_id, Task.task_number == task_number)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] task {task_number} already exists")
        return existing
    task = work_order_service.create_task(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        payload=TaskCreateRequest(work_order_id=work_order_id, task_number=task_number, **kwargs),
    )
    print(f"  [created] task {task_number}")
    return task


def _get_or_create_finding(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, title: str, **kwargs):
    from app.models.finding import Finding

    existing = db.execute(
        select(Finding).where(Finding.organization_id == org_id, Finding.title == title)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] finding {title!r} already exists")
        return existing
    finding = finding_service.create_finding(db, organization_id=org_id, actor_user_id=actor_id, title=title, **kwargs)
    print(f"  [created] finding {title!r}")
    return finding


def _get_or_create_regulatory_requirement(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, requirement_number: str, **kwargs):
    from app.models.compliance import RegulatoryRequirement

    existing = db.execute(
        select(RegulatoryRequirement).where(
            RegulatoryRequirement.organization_id == org_id,
            RegulatoryRequirement.requirement_number == requirement_number,
        )
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] regulatory requirement {requirement_number} already exists")
        return existing
    requirement = compliance_service.create_requirement(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        payload=RegulatoryRequirementCreateRequest(requirement_number=requirement_number, **kwargs),
    )
    print(f"  [created] regulatory requirement {requirement_number}")
    return requirement


def _get_or_create_compliance_assessment(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, aircraft_id: uuid.UUID, requirement_id: uuid.UUID, status: str, notes: str):
    from app.models.compliance import ComplianceAssessment

    existing = db.execute(
        select(ComplianceAssessment).where(
            ComplianceAssessment.organization_id == org_id,
            ComplianceAssessment.aircraft_id == aircraft_id,
            ComplianceAssessment.requirement_id == requirement_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] compliance assessment for aircraft already exists")
        return existing
    assessment = compliance_service.create_assessment(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft_id,
            requirement_id=requirement_id,
            status=status,
            evaluated_at=date.today(),
            notes=notes,
        ),
    )
    print(f"  [created] compliance assessment ({status})")
    return assessment


def _get_or_create_part(db: Session, *, org_id: uuid.UUID, actor_id: uuid.UUID, part_number: str, **kwargs):
    existing = db.execute(
        select(Part).where(Part.organization_id == org_id, Part.part_number == part_number)
    ).scalar_one_or_none()
    if existing is not None:
        print(f"  [skip] part {part_number} already exists")
        return existing
    part = part_service.create_part(
        db,
        organization_id=org_id,
        actor_user_id=actor_id,
        payload=PartCreateRequest(part_number=part_number, **kwargs),
    )
    print(f"  [created] part {part_number}")
    return part


def run(db: Session) -> None:
    org = db.get(Organization, QA_ORG_ID)
    if org is None:
        print(f"Organization {QA_ORG_ID} not found -- provision it first.", file=sys.stderr)
        sys.exit(1)
    print(f"Seeding QA dataset into organization: {org.name} ({org.id})")

    org_admin = db.execute(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.organization_id == org.id, UserRole.role_name == Role.ORG_ADMIN.value)
    ).scalars().first()
    if org_admin is None:
        print("No ORG_ADMIN found in this organization -- provision one first.", file=sys.stderr)
        sys.exit(1)
    actor_id = org_admin.id

    print("\n== QA USERS ==")
    # No TECHNICIAN/INSPECTOR/PILOT Role exists in this codebase's RBAC
    # model (app/core/permissions.py) -- CAMO_MANAGER/MAINTENANCE_ENGINEER/
    # QUALITY_MANAGER/VIEWER are the real tenant roles. "Pilot" and
    # "Technician" are operational job titles here, not RBAC roles: the
    # domain models (Mission.pilot_user_id, Task.assigned_technician_user_id)
    # accept any user in the org regardless of their RBAC role, exactly like
    # a real org would let its CAMO_MANAGER also fly a mission.
    maintenance_manager = _get_or_create_user(
        db, org_id=org.id, actor_id=actor_id,
        email="qa-maintenance-manager@kotas-aerospace-qa.com",
        full_name="QA Maintenance Manager", role=Role.CAMO_MANAGER.value,
    )
    maintenance_engineer = _get_or_create_user(
        db, org_id=org.id, actor_id=actor_id,
        email="qa-maintenance-engineer@kotas-aerospace-qa.com",
        full_name="QA Maintenance Engineer", role=Role.MAINTENANCE_ENGINEER.value,
    )
    technician = _get_or_create_user(
        db, org_id=org.id, actor_id=actor_id,
        email="qa-technician@kotas-aerospace-qa.com",
        full_name="QA Technician", role=Role.MAINTENANCE_ENGINEER.value,
    )
    inspector = _get_or_create_user(
        db, org_id=org.id, actor_id=actor_id,
        email="qa-inspector@kotas-aerospace-qa.com",
        full_name="QA Inspector", role=Role.QUALITY_MANAGER.value,
    )
    pilot = _get_or_create_user(
        db, org_id=org.id, actor_id=actor_id,
        email="qa-pilot@kotas-aerospace-qa.com",
        full_name="QA Pilot", role=Role.VIEWER.value,
    )
    viewer = _get_or_create_user(
        db, org_id=org.id, actor_id=actor_id,
        email="qa-viewer@kotas-aerospace-qa.com",
        full_name="QA Viewer", role=Role.VIEWER.value,
    )

    print("\n== AIRCRAFT ==")
    aircraft_1 = _get_or_create_aircraft(
        db, org_id=org.id, actor_id=actor_id,
        registration="VT-QA01", msn="QA320001", aircraft_type="A320-200", manufacturer="Airbus",
    )
    aircraft_2 = _get_or_create_aircraft(
        db, org_id=org.id, actor_id=actor_id,
        registration="VT-QA02", msn="QA320002", aircraft_type="A320neo", manufacturer="Airbus",
    )

    print("\n== DRONES ==")
    # AssetLifecycleStatus (app/models/asset.py) has no exact
    # MAINTENANCE_DUE/UNDER_INSPECTION/AWAITING_PARTS members -- the closest
    # real enum values are used instead (MAINTENANCE, INSPECTION, GROUNDED),
    # per this task's instruction to use actual schema values rather than
    # invent new ones. "Awaiting parts" is instead represented by the real
    # underlying condition the readiness engine would derive it from: a
    # Part row with zero stock required by that drone (see PARTS section).
    drone_1 = _get_or_create_drone(db, org_id=org.id, actor_id=actor_id, registration="KQA-UAV-001", manufacturer="KOTA Aerospace", model="Q-Wing X1", serial_number="SN-KQA-UAV-001")
    drone_2 = _get_or_create_drone(db, org_id=org.id, actor_id=actor_id, registration="KQA-UAV-002", manufacturer="KOTA Aerospace", model="Q-Wing X1", serial_number="SN-KQA-UAV-002")
    drone_3 = _get_or_create_drone(db, org_id=org.id, actor_id=actor_id, registration="KQA-UAV-003", manufacturer="KOTA Aerospace", model="Q-Wing X1", serial_number="SN-KQA-UAV-003")
    drone_4 = _get_or_create_drone(db, org_id=org.id, actor_id=actor_id, registration="KQA-UAV-004", manufacturer="KOTA Aerospace", model="Q-Wing X2", serial_number="SN-KQA-UAV-004")
    drone_5 = _get_or_create_drone(db, org_id=org.id, actor_id=actor_id, registration="KQA-UAV-005", manufacturer="KOTA Aerospace", model="Q-Wing X2", serial_number="SN-KQA-UAV-005")

    for asset, status in (
        (drone_2, "MAINTENANCE"),
        (drone_3, "GROUNDED"),
        (drone_4, "INSPECTION"),
        (drone_5, "MAINTENANCE"),
    ):
        if asset.status != status:
            asset.status = status
            db.add(asset)
    db.commit()
    print("  [state] drone statuses distributed: 001=ACTIVE, 002=MAINTENANCE, 003=GROUNDED, 004=INSPECTION, 005=MAINTENANCE")

    print("\n== COMPONENTS ==")
    _get_or_create_component(db, org_id=org.id, asset_id=aircraft_1.asset_id, component_type=ComponentType.ENGINE, name="Engine #1", serial_number="ENG-QA01-1", status=ComponentStatus.INSTALLED)
    _get_or_create_component(db, org_id=org.id, asset_id=aircraft_1.asset_id, component_type=ComponentType.LANDING_GEAR, name="Main Landing Gear", serial_number="LG-QA01-1", status=ComponentStatus.INSTALLED)
    brake = _get_or_create_component(db, org_id=org.id, asset_id=aircraft_1.asset_id, component_type=ComponentType.HYDRAULIC, name="Brake Assembly", serial_number="BRK-QA01-1", status=ComponentStatus.INSTALLED)
    motor_2 = _get_or_create_component(db, org_id=org.id, asset_id=drone_3.id, component_type=ComponentType.MOTOR, name="Motor #2", serial_number="MOT-KQA003-2", status=ComponentStatus.IN_MAINTENANCE)
    _get_or_create_component(db, org_id=org.id, asset_id=drone_3.id, component_type=ComponentType.PROPELLER, name="Propeller #2", serial_number="PROP-KQA003-2", status=ComponentStatus.INSTALLED)
    _get_or_create_component(db, org_id=org.id, asset_id=drone_1.id, component_type=ComponentType.FLIGHT_CONTROLLER, name="Flight Controller", serial_number="FC-KQA001-1", status=ComponentStatus.INSTALLED)

    print("\n== BATTERIES ==")
    _get_or_create_battery(db, org_id=org.id, serial_number="BAT-KQA-001", asset_id=drone_1.id, status=BatteryStatus.GOOD, health_percent=96)
    _get_or_create_battery(db, org_id=org.id, serial_number="BAT-KQA-002", asset_id=drone_2.id, status=BatteryStatus.MONITOR, health_percent=78)
    _get_or_create_battery(db, org_id=org.id, serial_number="BAT-KQA-003", asset_id=drone_3.id, status=BatteryStatus.SERVICE_DUE, health_percent=61)
    _get_or_create_battery(db, org_id=org.id, serial_number="BAT-KQA-004", asset_id=None, status=BatteryStatus.CRITICAL, health_percent=22)

    print("\n== MISSIONS ==")
    mission_1 = _get_or_create_mission(db, org_id=org.id, actor_id=actor_id, asset_id=drone_1.id, pilot_id=pilot.id, purpose="Infrastructure Inspection", operating_area="KQA Test Range North")
    mission_2 = _get_or_create_mission(db, org_id=org.id, actor_id=actor_id, asset_id=drone_2.id, pilot_id=pilot.id, purpose="Powerline Survey", operating_area="KQA Test Range East")

    print("\n== FLIGHTS ==")
    _get_or_create_flight(db, org_id=org.id, actor_id=actor_id, asset_id=drone_1.id, mission_id=mission_1.id, pilot_id=pilot.id, flight_number="KQA-FLT-0001", duration_minutes=84)
    _get_or_create_flight(db, org_id=org.id, actor_id=actor_id, asset_id=drone_1.id, mission_id=mission_1.id, pilot_id=pilot.id, flight_number="KQA-FLT-0002", duration_minutes=52)
    _get_or_create_flight(db, org_id=org.id, actor_id=actor_id, asset_id=drone_2.id, mission_id=mission_2.id, pilot_id=pilot.id, flight_number="KQA-FLT-0003", duration_minutes=67)

    print("\n== WORK ORDERS ==")
    wo_drone = _get_or_create_work_order(
        db, org_id=org.id, actor_id=actor_id, work_order_number="WO-KQA-001",
        asset_id=drone_3.id, title="Drone Motor Vibration Investigation",
        description="Elevated vibration reported on Motor #2 during post-flight inspection.",
        work_order_type="CORRECTIVE", status="IN_PROGRESS", priority="HIGH",
        assigned_to_user_id=technician.id,
    )
    wo_aircraft = _get_or_create_work_order(
        db, org_id=org.id, actor_id=actor_id, work_order_number="WO-KQA-002",
        aircraft_id=aircraft_1.id, title="Aircraft Brake Inspection",
        description="Scheduled brake wear inspection ahead of next compliance cycle.",
        work_order_type="INSPECTION", status="INSPECTION", priority="NORMAL",
        assigned_to_user_id=maintenance_engineer.id,
    )

    print("\n== TASKS ==")
    task_drone = _get_or_create_task(
        db, org_id=org.id, actor_id=actor_id, work_order_id=wo_drone.id, task_number="TASK-KQA-001-1",
        title="Inspect and replace Motor #2", description="Remove, inspect, and replace vibrating motor.",
        execution_state="IN_PROGRESS", assigned_technician_user_id=technician.id, evidence_required=True,
    )
    task_aircraft = _get_or_create_task(
        db, org_id=org.id, actor_id=actor_id, work_order_id=wo_aircraft.id, task_number="TASK-KQA-002-1",
        title="Brake pad wear measurement", description="Measure remaining brake pad thickness against service limit.",
        execution_state="PENDING", assigned_technician_user_id=maintenance_engineer.id, evidence_required=True,
    )

    print("\n== FINDINGS ==")
    finding_1 = _get_or_create_finding(
        db, org_id=org.id, actor_id=actor_id, title="Elevated vibration detected",
        description="Motor #2 vibration exceeds threshold during pre-flight check.",
        severity="MAJOR", asset_id=drone_3.id, component_id=motor_2.id, work_order_id=wo_drone.id,
        task_id=task_drone.id, responsible_user_id=technician.id,
    )
    finding_2 = _get_or_create_finding(
        db, org_id=org.id, actor_id=actor_id, title="Brake wear approaching service limit",
        description="Brake pad thickness measured near minimum service limit.",
        severity="MINOR", aircraft_id=aircraft_1.id, component_id=brake.id, work_order_id=wo_aircraft.id,
        task_id=task_aircraft.id, responsible_user_id=maintenance_engineer.id,
    )

    print("\n== INSPECTIONS ==")
    from app.models.inspection_requirement import InspectionRequirement
    def _inspection(task_id, work_order_id, required):
        existing = db.execute(
            select(InspectionRequirement).where(
                InspectionRequirement.organization_id == org.id,
                InspectionRequirement.task_id == task_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [skip] inspection requirement for task already exists")
            return existing
        created = inspection_service.create_inspection_requirement(
            db, organization_id=org.id, task_id=task_id, work_order_id=work_order_id, required=required,
        )
        print(f"  [created] inspection requirement (task={task_id})")
        return created

    insp_1 = _inspection(task_drone.id, wo_drone.id, True)
    insp_1.inspector_user_id = inspector.id
    insp_1.status = "COMPLETED"
    insp_2 = _inspection(task_aircraft.id, wo_aircraft.id, True)
    insp_2.inspector_user_id = inspector.id
    insp_2.status = "PENDING"
    db.add(insp_1)
    db.add(insp_2)
    db.commit()

    print("\n== EVIDENCE ==")
    from app.models.evidence import Evidence, EvidenceStatus
    def _evidence(title, **kw):
        existing = db.execute(
            select(Evidence).where(Evidence.organization_id == org.id, Evidence.title == title)
        ).scalar_one_or_none()
        if existing is not None:
            print(f"  [skip] evidence {title!r} already exists")
            return existing
        created = evidence_service.create_evidence(db, organization_id=org.id, title=title, **kw)
        print(f"  [created] evidence {title!r}")
        return created

    ev1 = _evidence(
        "Motor #2 removal photograph", task_id=task_drone.id, asset_id=drone_3.id,
        component_id=motor_2.id, finding_id=finding_1.id, work_order_id=wo_drone.id,
        uploaded_by_user_id=technician.id, evidence_type="PHOTOGRAPH",
        description="Photograph of removed Motor #2 showing visible wear.",
    )
    ev1.status = EvidenceStatus.ACCEPTED
    ev1.reviewer_user_id = inspector.id
    db.add(ev1)
    ev2 = _evidence(
        "Brake pad thickness measurement", task_id=task_aircraft.id, aircraft_id=aircraft_1.id,
        component_id=brake.id, finding_id=finding_2.id, work_order_id=wo_aircraft.id,
        uploaded_by_user_id=maintenance_engineer.id, evidence_type="TEST_RESULT",
        description="Measured brake pad thickness: 4.2mm (service limit 4.0mm).",
    )
    ev2.status = EvidenceStatus.SUBMITTED
    db.add(ev2)
    db.commit()

    print("\n== COMPLIANCE ==")
    requirement = _get_or_create_regulatory_requirement(
        db, org_id=org.id, actor_id=actor_id, requirement_number="QA-REQ-INSP-001",
        authority="DGCA", title="Inspection interval compliance",
        description="Periodic airworthiness inspection interval requirement (synthetic QA requirement).",
        effective_date=date.today() - timedelta(days=365),
    )
    _get_or_create_compliance_assessment(
        db, org_id=org.id, actor_id=actor_id, aircraft_id=aircraft_1.id, requirement_id=requirement.id,
        status="COMPLIANT", notes="Synthetic QA assessment: current inspection cycle satisfied.",
    )
    _get_or_create_compliance_assessment(
        db, org_id=org.id, actor_id=actor_id, aircraft_id=aircraft_2.id, requirement_id=requirement.id,
        status="REVIEW_REQUIRED", notes="Synthetic QA assessment: component inspection due for review.",
    )

    print("\n== PARTS / INVENTORY ==")
    _get_or_create_part(
        db, org_id=org.id, actor_id=actor_id, part_number="PROP-22-001",
        description="22-inch carbon fiber propeller, replacement for KQA-UAV-003 Motor #2 assembly.",
        manufacturer="KOTA Aerospace QA Parts", condition="NEW", quantity_on_hand=0,
    )

    print("\nQA seed complete.")
    print(f"Organization: {org.name} ({org.id})")
    print("Rerun this script anytime -- every entity above is looked up by a stable natural key first.")


def main() -> None:
    _guard_environment()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()
    try:
        run(db)
    except AeroComplyError as exc:
        print(f"Seed failed: {exc.code}: {exc.message}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
