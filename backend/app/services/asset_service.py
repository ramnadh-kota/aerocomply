"""M4: Common Aerospace Domain Foundation Service.

Provides domain-neutral asset operations across all aerospace asset types
(Fixed-Wing Aircraft, Drone UAVs, Rotorcraft/Helicopters, and extensible eVTOL/AAM).

Enforces strict tenant isolation (derived from current_user.organization_id)
and respects domain boundaries.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.aircraft_detail import AircraftDetail
from app.models.asset import Asset, AssetLifecycleStatus, AssetOperationalStatus, AssetType
from app.models.audit_event import AuditEvent
from app.models.battery import Battery
from app.models.compliance import ComplianceAssessment, ComplianceAssessmentStatus
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.finding import Finding, FindingStatus
from app.models.flight import Flight
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus
from app.models.installation_history import ComponentInstallation
from app.models.maintenance_requirement import MaintenanceAccomplishment
from app.models.mission import Mission, MissionStatus
from app.models.task import Task
from app.models.work_order import WorkOrder
from app.services.limit_enforcement_service import check_asset_creation_limit
from app.schemas.asset import (
    AssetComponentResponse,
    AssetConfigurationResponse,
    AssetConfigurationSlotResponse,
    AssetCreateRequest,
    AssetDomainContextResponse,
    AssetFlightCreateRequest,
    AssetFlightResponse,
    AssetHistoryEventResponse,
    AssetHistoryResponse,
    AssetInstallComponentRequest,
    AssetOperationsResponse,
    AssetReadinessResponse,
    AssetResponse,
    AssetUpdateRequest,
    AssetUtilizationResponse,
    ReadinessDimension,
    UsageMetricItem,
)
from app.services.audit_service import record_audit_event


def get_asset(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> Asset:
    """Retrieve an asset by ID strictly scoped to the caller's organization.

    Excludes soft-deleted rows (deleted_at IS NOT NULL) -- a tenant that
    deleted an asset must never be able to keep reading it through this or
    any function built on it (get_aircraft_asset, readiness, history, ...).
    Platform Admin's deletion_service/restoration_service query Asset
    directly instead of through this function, precisely so they CAN see
    soft-deleted rows.
    """
    asset = db.execute(
        select(Asset).where(
            Asset.id == asset_id,
            Asset.organization_id == organization_id,
            Asset.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if asset is None:
        raise NotFoundError("Asset not found")
    return asset


def list_assets(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
) -> list[Asset]:
    """List assets for an organization with optional type, status, and search filters.

    Excludes soft-deleted rows -- see get_asset's docstring.
    """
    query = select(Asset).where(
        Asset.organization_id == organization_id, Asset.deleted_at.is_(None)
    )

    if asset_type is not None:
        query = query.where(Asset.asset_type == asset_type.upper())

    if status is not None:
        query = query.where(Asset.status == status.upper())

    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            (Asset.registration.ilike(pattern))
            | (Asset.manufacturer.ilike(pattern))
            | (Asset.model.ilike(pattern))
            | (Asset.serial_number.ilike(pattern))
        )

    query = query.order_by(Asset.registration.asc().nulls_last(), Asset.created_at.desc())
    return list(db.execute(query).scalars().all())


def create_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: AssetCreateRequest,
) -> Asset:
    """Create a new aerospace asset within tenant scope."""
    check_asset_creation_limit(db, organization_id=organization_id)

    # Check registration uniqueness within organization
    existing = db.execute(
        select(Asset).where(
            Asset.organization_id == organization_id,
            Asset.registration == payload.registration.strip().upper(),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(
            f"Asset registration {payload.registration!r} is already in use.",
            code="duplicate_registration",
        )

    # Normalize asset type
    normalized_type = payload.asset_type.strip().upper()

    asset = Asset(
        id=uuid.uuid4(),
        organization_id=organization_id,
        asset_type=normalized_type,
        registration=payload.registration.strip().upper(),
        manufacturer=payload.manufacturer.strip() if payload.manufacturer else None,
        model=payload.model.strip() if payload.model else None,
        serial_number=payload.serial_number.strip() if payload.serial_number else None,
        facility_id=payload.facility_id,
        status=payload.status.strip().upper() if payload.status else AssetLifecycleStatus.ACTIVE.value,
        acquired_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    db.add(asset)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="asset.created",
        entity_type="Asset",
        entity_id=asset.id,
        metadata={
            "registration": asset.registration,
            "asset_type": asset.asset_type,
            "manufacturer": asset.manufacturer,
            "model": asset.model,
        },
    )
    db.commit()
    db.refresh(asset)
    return asset


def update_asset(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    payload: AssetUpdateRequest,
) -> Asset:
    """Update asset metadata and status within tenant scope."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    changed_fields = {}
    if payload.manufacturer is not None:
        asset.manufacturer = payload.manufacturer.strip()
        changed_fields["manufacturer"] = asset.manufacturer
    if payload.model is not None:
        asset.model = payload.model.strip()
        changed_fields["model"] = asset.model
    if payload.serial_number is not None:
        asset.serial_number = payload.serial_number.strip()
        changed_fields["serial_number"] = asset.serial_number
    if payload.facility_id is not None:
        asset.facility_id = payload.facility_id
        changed_fields["facility_id"] = str(asset.facility_id)
    if payload.status is not None:
        asset.status = payload.status.strip().upper()
        changed_fields["status"] = asset.status

    if changed_fields:
        record_audit_event(
            db,
            organization_id=organization_id,
            user_id=actor_user_id,
            action="asset.updated",
            entity_type="Asset",
            entity_id=asset.id,
            metadata=changed_fields,
        )
        db.commit()
        db.refresh(asset)

    return asset


def get_aircraft_asset(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> Asset:
    """Resolve the Asset backing a given Aircraft."""
    aircraft = db.execute(
        select(Aircraft).where(
            Aircraft.id == aircraft_id, Aircraft.organization_id == organization_id
        )
    ).scalar_one_or_none()
    if aircraft is None or aircraft.asset_id is None:
        raise NotFoundError("Asset not found for this aircraft")
    return get_asset(db, organization_id=organization_id, asset_id=aircraft.asset_id)


# ---------------------------------------------------------------------------
# Configuration & Components
# ---------------------------------------------------------------------------

def get_asset_configuration(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetConfigurationResponse:
    """Standardized configuration representation across all asset types."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # Installed components on this asset
    components = list(
        db.execute(
            select(Component)
            .where(
                Component.asset_id == asset.id,
                Component.organization_id == organization_id,
                Component.status == ComponentStatus.INSTALLED,
            )
            .order_by(Component.component_type.asc(), Component.name.asc())
        ).scalars().all()
    )

    airframe_spec: dict[str, Any] = {
        "asset_type": asset.asset_type,
        "manufacturer": asset.manufacturer,
        "model": asset.model,
        "serial_number": asset.serial_number,
        "registration": asset.registration,
    }

    if asset.asset_type == AssetType.AIRCRAFT.value:
        detail = db.execute(
            select(AircraftDetail).where(AircraftDetail.asset_id == asset.id)
        ).scalar_one_or_none()
        if detail:
            airframe_spec["msn"] = detail.msn
            airframe_spec["aircraft_type"] = detail.aircraft_type

    # Build standardized configuration slots based on asset domain
    slots: list[AssetConfigurationSlotResponse] = []
    
    if asset.asset_type == AssetType.DRONE.value:
        standard_slots = [
            ("Propulsion System (Motors)", ComponentType.MOTOR),
            ("Speed Controllers (ESCs)", ComponentType.ESC),
            ("Propeller Set", ComponentType.PROPELLER),
            ("Flight Controller", ComponentType.FLIGHT_CONTROLLER),
            ("Navigation GNSS/GPS", ComponentType.GPS),
            ("Sensor / Camera Payload", ComponentType.CAMERA),
            ("Gimbal Stabilization", ComponentType.GIMBAL),
            ("Telemetry Radio", ComponentType.RADIO),
        ]
    elif asset.asset_type == AssetType.HELICOPTER.value:
        standard_slots = [
            ("Main Rotor Assembly", ComponentType.ROTOR),
            ("Tail Rotor System", ComponentType.ROTOR),
            ("Turbine Engine 1", ComponentType.ENGINE),
            ("Main Transmission / Gearbox", ComponentType.TRANSMISSION),
            ("Integrated Avionics Suite", ComponentType.AVIONICS),
            ("Flight Control Actuators", ComponentType.ACTUATOR),
            ("Hydraulic System", ComponentType.HYDRAULIC),
            ("Primary Sensor Payload", ComponentType.SENSOR),
        ]
    else:  # AIRCRAFT, EVTOL, OTHER
        standard_slots = [
            ("Engine Position 1 (Left)", ComponentType.ENGINE),
            ("Engine Position 2 (Right)", ComponentType.ENGINE),
            ("Auxiliary Power Unit (APU)", ComponentType.APU),
            ("Primary Flight Avionics", ComponentType.AVIONICS),
            ("Flight Management Computer", ComponentType.FLIGHT_CONTROLLER),
            ("Landing Gear Assembly", ComponentType.LANDING_GEAR),
            ("Hydraulic Power Unit", ComponentType.HYDRAULIC),
            ("Navigation / Comms Suite", ComponentType.RADIO),
        ]

    # Map installed components to matching slot types
    matched_component_ids = set()
    for slot_name, c_type in standard_slots:
        comp_match = next(
            (c for c in components if c.component_type == c_type and c.id not in matched_component_ids),
            None,
        )
        if comp_match:
            matched_component_ids.add(comp_match.id)
            slots.append(
                AssetConfigurationSlotResponse(
                    slot_name=slot_name,
                    component_type=c_type,
                    is_occupied=True,
                    component=AssetComponentResponse.model_validate(comp_match),
                )
            )
        else:
            slots.append(
                AssetConfigurationSlotResponse(
                    slot_name=slot_name,
                    component_type=c_type,
                    is_occupied=False,
                    component=None,
                )
            )

    # Any remaining installed components
    for comp in components:
        if comp.id not in matched_component_ids:
            slots.append(
                AssetConfigurationSlotResponse(
                    slot_name=f"Custom: {comp.name}",
                    component_type=comp.component_type,
                    is_occupied=True,
                    component=AssetComponentResponse.model_validate(comp),
                )
            )

    return AssetConfigurationResponse(
        asset_id=asset.id,
        asset_type=asset.asset_type,
        airframe_spec=airframe_spec,
        slots=slots,
        total_components_installed=len(components),
    )


def get_asset_components(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> list[AssetComponentResponse]:
    """List components installed or assigned to this asset."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)
    components = db.execute(
        select(Component)
        .where(Component.asset_id == asset_id, Component.organization_id == organization_id)
        .order_by(Component.component_type.asc(), Component.name.asc())
    ).scalars().all()
    return [AssetComponentResponse.model_validate(c) for c in components]


def install_asset_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    payload: AssetInstallComponentRequest,
) -> AssetComponentResponse:
    """Install a component onto an asset within tenant scope."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    component = Component(
        id=uuid.uuid4(),
        organization_id=organization_id,
        asset_id=asset.id,
        component_type=payload.component_type.strip().upper(),
        name=payload.name.strip(),
        serial_number=payload.serial_number.strip() if payload.serial_number else None,
        manufacturer=payload.manufacturer.strip() if payload.manufacturer else None,
        model=payload.model.strip() if payload.model else None,
        status=ComponentStatus.INSTALLED,
        notes=payload.notes.strip() if payload.notes else None,
        created_at=datetime.now(UTC),
    )
    db.add(component)
    db.flush()

    # Track installation history
    install_history = ComponentInstallation(
        id=uuid.uuid4(),
        organization_id=organization_id,
        component_id=component.id,
        asset_id=asset.id,
        installed_at=datetime.now(UTC),
        installed_by=actor_user_id,
        created_at=datetime.now(UTC),
    )
    db.add(install_history)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="asset.component.installed",
        entity_type="Asset",
        entity_id=asset.id,
        metadata={
            "component_id": str(component.id),
            "component_type": component.component_type,
            "component_name": component.name,
            "serial_number": component.serial_number,
        },
    )
    db.commit()
    db.refresh(component)
    return AssetComponentResponse.model_validate(component)


def remove_asset_component(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    component_id: uuid.UUID,
) -> AssetComponentResponse:
    """Remove an installed component from an asset."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)

    component = db.execute(
        select(Component).where(
            Component.id == component_id,
            Component.asset_id == asset_id,
            Component.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if component is None:
        raise NotFoundError("Component not found on this asset")

    component.status = ComponentStatus.REMOVED
    component.asset_id = None

    # Close open installation history row
    open_install = db.execute(
        select(ComponentInstallation).where(
            ComponentInstallation.component_id == component_id,
            ComponentInstallation.asset_id == asset_id,
            ComponentInstallation.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if open_install:
        open_install.removed_at = datetime.now(UTC)
        open_install.removed_by = actor_user_id

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="asset.component.removed",
        entity_type="Asset",
        entity_id=asset_id,
        metadata={
            "component_id": str(component.id),
            "component_name": component.name,
        },
    )
    db.commit()
    db.refresh(component)
    return AssetComponentResponse.model_validate(component)


# ---------------------------------------------------------------------------
# Operations & Utilization
# ---------------------------------------------------------------------------

def get_asset_utilization(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetUtilizationResponse:
    """Compute usage metrics across flight hours, cycles, and landings."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    stats = db.execute(
        select(
            func.count(Flight.id),
            func.coalesce(func.sum(Flight.duration_minutes), 0),
            func.coalesce(func.sum(Flight.cycles), 0),
        ).where(Flight.asset_id == asset.id, Flight.organization_id == organization_id)
    ).one()

    total_flights = int(stats[0])
    total_minutes = int(stats[1])
    total_cycles = int(stats[2])
    total_flight_hours = round(total_minutes / 60.0, 2)
    total_landings = total_cycles  # 1 cycle = 1 flight/landing cycle standard

    metrics = [
        UsageMetricItem(
            metric_key="TOTAL_FLIGHT_HOURS",
            metric_label="Airframe Time in Service",
            value=total_flight_hours,
            unit="hours",
            source="FLIGHT",
            is_metered=True,
        ),
        UsageMetricItem(
            metric_key="TOTAL_CYCLES",
            metric_label="Flight Operating Cycles",
            value=float(total_cycles),
            unit="cycles",
            source="FLIGHT",
            is_metered=True,
        ),
        UsageMetricItem(
            metric_key="TOTAL_FLIGHTS",
            metric_label="Completed Sorties / Sectors",
            value=float(total_flights),
            unit="sorties",
            source="FLIGHT",
            is_metered=True,
        ),
        UsageMetricItem(
            metric_key="TOTAL_LANDINGS",
            metric_label="Total Landing Touchdowns",
            value=float(total_landings),
            unit="landings",
            source="FLIGHT",
            is_metered=True,
        ),
    ]

    return AssetUtilizationResponse(
        asset_id=asset.id,
        asset_type=asset.asset_type,
        total_flight_hours=total_flight_hours,
        total_minutes=total_minutes,
        total_cycles=total_cycles,
        total_flights=total_flights,
        total_landings=total_landings,
        metrics=metrics,
    )


def record_asset_flight(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    asset_id: uuid.UUID,
    payload: AssetFlightCreateRequest,
) -> AssetFlightResponse:
    """Record an operational flight log entry for any non-drone asset type.

    DRONE assets must use POST /drones/{asset_id}/flights (flight_service.
    record_flight) instead: that path atomically increments the attached
    battery's cycle_count so it can never drift from actual flight history
    (see flight_service.py's docstring for the concurrency hardening this
    required). This generic path has no equivalent battery bookkeeping, so
    routing a drone's flight through it would silently produce an
    under-counted battery -- rejecting it here keeps there being exactly one
    way to record a drone flight, rather than two paths that can disagree.
    """
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)
    if asset.asset_type == AssetType.DRONE.value:
        raise AeroComplyError(
            "Drone flights must be recorded via POST /drones/{asset_id}/flights, "
            "which also maintains attached battery cycle counts.",
            code="use_drone_flight_endpoint",
        )

    flight = Flight(
        id=uuid.uuid4(),
        organization_id=organization_id,
        asset_id=asset.id,
        mission_id=payload.mission_id,
        flown_at=payload.flown_at,
        duration_minutes=payload.duration_minutes,
        cycles=payload.cycles,
        pilot_user_id=payload.pilot_user_id or actor_user_id,
        notes=payload.notes.strip() if payload.notes else None,
        created_at=datetime.now(UTC),
    )
    db.add(flight)
    db.flush()

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="asset.flight_recorded",
        entity_type="Asset",
        entity_id=asset.id,
        metadata={
            "flight_id": str(flight.id),
            "duration_minutes": flight.duration_minutes,
            "cycles": flight.cycles,
        },
    )
    db.commit()
    db.refresh(flight)
    return AssetFlightResponse.model_validate(flight)


def get_asset_operations(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetOperationsResponse:
    """Retrieve operational event summaries, recent flights, and active missions."""
    utilization = get_asset_utilization(db, organization_id=organization_id, asset_id=asset_id)

    flights = list(
        db.execute(
            select(Flight)
            .where(Flight.asset_id == asset_id, Flight.organization_id == organization_id)
            .order_by(Flight.flown_at.desc())
            .limit(10)
        ).scalars().all()
    )

    missions = list(
        db.execute(
            select(Mission)
            .where(Mission.asset_id == asset_id, Mission.organization_id == organization_id)
            .order_by(Mission.created_at.desc())
            .limit(5)
        ).scalars().all()
    )

    active_missions = [
        {
            "id": str(m.id),
            "purpose": m.purpose,
            "status": m.status,
            "operating_area": m.operating_area,
            "planned_start": m.planned_start.isoformat() if m.planned_start else None,
        }
        for m in missions
    ]

    return AssetOperationsResponse(
        asset_id=asset_id,
        utilization=utilization,
        recent_flights=[AssetFlightResponse.model_validate(f) for f in flights],
        active_missions=active_missions,
    )


# ---------------------------------------------------------------------------
# Maintenance, Inspections, Evidence, Findings, Compliance
# ---------------------------------------------------------------------------

def get_asset_maintenance(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve maintenance state, open work orders, and accomplishment history."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # Open work orders linked to this asset
    work_orders = list(
        db.execute(
            select(WorkOrder)
            .where(
                WorkOrder.asset_id == asset_id,
                WorkOrder.organization_id == organization_id,
                WorkOrder.deleted_at.is_(None),
            )
            .order_by(WorkOrder.created_at.desc())
        ).scalars().all()
    )

    # Maintenance accomplishments on this asset
    accomplishments = list(
        db.execute(
            select(MaintenanceAccomplishment)
            .where(
                MaintenanceAccomplishment.asset_id == asset_id,
                MaintenanceAccomplishment.organization_id == organization_id,
            )
            .order_by(MaintenanceAccomplishment.accomplished_at.desc())
            .limit(20)
        ).scalars().all()
    )

    has_overdue = any(wo.priority == "CRITICAL" for wo in work_orders if wo.status != "COMPLETED")

    return {
        "asset_id": str(asset_id),
        "open_work_orders": [
            {
                "id": str(wo.id),
                "work_order_number": wo.work_order_number,
                "status": wo.status,
                "priority": wo.priority,
                "created_at": wo.created_at.isoformat(),
            }
            for wo in work_orders
        ],
        "accomplishments": [
            {
                "id": str(acc.id),
                "requirement_id": str(acc.requirement_id),
                "accomplished_at": acc.accomplished_at.isoformat(),
                "work_order_id": str(acc.work_order_id) if acc.work_order_id else None,
                "notes": acc.notes,
            }
            for acc in accomplishments
        ],
        "has_overdue": has_overdue,
    }


def get_asset_inspections(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve inspection requirements attached to this asset's work order chain."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # Join through tasks and work orders
    inspections = list(
        db.execute(
            select(InspectionRequirement)
            .join(WorkOrder, InspectionRequirement.work_order_id == WorkOrder.id)
            .where(
                WorkOrder.asset_id == asset_id,
                InspectionRequirement.organization_id == organization_id,
            )
            .order_by(InspectionRequirement.created_at.desc())
        ).scalars().all()
    )

    completed = sum(1 for i in inspections if i.status == InspectionRequirementStatus.COMPLETED.value)
    pending = sum(1 for i in inspections if i.status == InspectionRequirementStatus.PENDING.value)

    return {
        "asset_id": str(asset_id),
        "inspections": [
            {
                "id": str(i.id),
                "work_order_id": str(i.work_order_id) if i.work_order_id else None,
                "task_id": str(i.task_id) if i.task_id else None,
                "status": i.status,
                "required": i.required,
                "rejection_reason": i.rejection_reason,
            }
            for i in inspections
        ],
        "total": len(inspections),
        "completed": completed,
        "pending": pending,
    }


def get_asset_evidence(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve evidence items associated with tasks on this asset."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)

    # Note: evidence connects to task -> work_order -> asset_id
    from app.models.evidence import Evidence
    evidence_items = list(
        db.execute(
            select(Evidence)
            .join(Task, Evidence.task_id == Task.id)
            .join(WorkOrder, Task.work_order_id == WorkOrder.id)
            .where(
                WorkOrder.asset_id == asset_id,
                Evidence.organization_id == organization_id,
            )
            .order_by(Evidence.created_at.desc())
        ).scalars().all()
    )

    accepted = sum(1 for e in evidence_items if e.status == "ACCEPTED")
    pending = sum(1 for e in evidence_items if e.status != "ACCEPTED")

    return {
        "asset_id": str(asset_id),
        "evidence_items": [
            {
                "id": str(e.id),
                "task_id": str(e.task_id),
                "status": e.status,
                "created_at": e.created_at.isoformat(),
            }
            for e in evidence_items
        ],
        "total": len(evidence_items),
        "accepted_count": accepted,
        "pending_count": pending,
    }


def get_asset_findings(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve all findings raised against this asset."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)

    findings = list(
        db.execute(
            select(Finding)
            .where(Finding.asset_id == asset_id, Finding.organization_id == organization_id)
            .order_by(Finding.discovered_at.desc())
        ).scalars().all()
    )

    open_count = sum(1 for f in findings if f.status != FindingStatus.CLOSED)
    closed_count = sum(1 for f in findings if f.status == FindingStatus.CLOSED)

    return {
        "asset_id": str(asset_id),
        "findings": [
            {
                "id": str(f.id),
                "title": f.title,
                "description": f.description,
                "severity": f.severity,
                "status": f.status,
                "discovered_at": f.discovered_at.isoformat(),
            }
            for f in findings
        ],
        "total": len(findings),
        "open_count": open_count,
        "closed_count": closed_count,
    }


def get_asset_compliance(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> dict[str, Any]:
    """Retrieve compliance assessments for this asset."""
    get_asset(db, organization_id=organization_id, asset_id=asset_id)

    assessments = list(
        db.execute(
            select(ComplianceAssessment)
            .where(
                ComplianceAssessment.asset_id == asset_id,
                ComplianceAssessment.organization_id == organization_id,
            )
            .order_by(ComplianceAssessment.evaluated_at.desc().nulls_last())
        ).scalars().all()
    )

    compliant_count = sum(1 for a in assessments if a.status == ComplianceAssessmentStatus.COMPLIANT)
    non_compliant_count = sum(1 for a in assessments if a.status == ComplianceAssessmentStatus.NON_COMPLIANT)

    if non_compliant_count > 0:
        overall_status = ComplianceAssessmentStatus.NON_COMPLIANT
    elif compliant_count > 0:
        overall_status = ComplianceAssessmentStatus.COMPLIANT
    else:
        overall_status = ComplianceAssessmentStatus.UNKNOWN

    return {
        "asset_id": str(asset_id),
        "assessments": [
            {
                "id": str(a.id),
                "requirement_id": str(a.requirement_id),
                "status": a.status,
                "evaluated_at": a.evaluated_at.isoformat() if a.evaluated_at else None,
                "notes": a.notes,
            }
            for a in assessments
        ],
        "overall_status": overall_status,
        "compliant_count": compliant_count,
        "non_compliant_count": non_compliant_count,
    }


# ---------------------------------------------------------------------------
# Multi-Dimensional Readiness
# ---------------------------------------------------------------------------

def get_asset_readiness(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetReadinessResponse:
    """Evaluate multi-dimensional operational, maintenance, compliance, deployment,
    and release readiness semantics without conflating them."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    dimensions: list[ReadinessDimension] = []
    overall_blockers: list[str] = []

    # 1. Operational Readiness
    op_blockers = []
    if asset.status == AssetLifecycleStatus.GROUNDED.value:
        op_blockers.append("Airframe is currently grounded.")
    elif asset.status == AssetLifecycleStatus.RETIRED.value:
        op_blockers.append("Airframe has been retired from service.")
    
    op_status = "BLOCKED" if op_blockers else "READY"
    dimensions.append(
        ReadinessDimension(
            dimension="OPERATIONAL",
            status=op_status,
            summary=f"Asset lifecycle state is {asset.status}.",
            blockers=op_blockers,
        )
    )
    overall_blockers.extend(op_blockers)

    # 2. Maintenance Readiness
    maint_data = get_asset_maintenance(db, organization_id=organization_id, asset_id=asset_id)
    maint_blockers = []
    critical_wos = [wo for wo in maint_data["open_work_orders"] if wo["priority"] == "CRITICAL"]
    if critical_wos:
        maint_blockers.append(f"{len(critical_wos)} critical open maintenance work orders pending.")
    if maint_data["has_overdue"]:
        maint_blockers.append("Overdue maintenance accomplishment intervals detected.")
    
    maint_status = "BLOCKED" if maint_blockers else "READY"
    dimensions.append(
        ReadinessDimension(
            dimension="MAINTENANCE",
            status=maint_status,
            summary="All scheduled maintenance accomplishments current." if not maint_blockers else "Maintenance actions required.",
            blockers=maint_blockers,
        )
    )
    overall_blockers.extend(maint_blockers)

    # 3. Compliance Readiness
    comp_data = get_asset_compliance(db, organization_id=organization_id, asset_id=asset_id)
    comp_blockers = []
    if comp_data["non_compliant_count"] > 0:
        comp_blockers.append(f"{comp_data['non_compliant_count']} non-compliant regulatory assessment determinations on file.")
    
    comp_status = "BLOCKED" if comp_blockers else ("READY" if comp_data["compliant_count"] > 0 else "AT_RISK")
    dimensions.append(
        ReadinessDimension(
            dimension="COMPLIANCE",
            status=comp_status,
            summary="All applicable airworthiness/regulatory rules compliant." if not comp_blockers else "Non-compliant regulatory directives.",
            blockers=comp_blockers,
        )
    )
    overall_blockers.extend(comp_blockers)

    # 4. Deployment Readiness
    dep_blockers = list(overall_blockers)
    dep_status = "BLOCKED" if dep_blockers else "READY"
    dimensions.append(
        ReadinessDimension(
            dimension="DEPLOYMENT",
            status=dep_status,
            summary="Eligible for operational sortie/flight dispatch." if not dep_blockers else "Deployment dispatch blocked.",
            blockers=dep_blockers,
        )
    )

    # 5. Release Readiness
    rel_status = "READY" if not overall_blockers else "BLOCKED"
    dimensions.append(
        ReadinessDimension(
            dimension="RELEASE",
            status=rel_status,
            summary="All evidence, inspection, and task gates satisfied." if not overall_blockers else "Work order release blockers pending.",
            blockers=overall_blockers,
        )
    )

    overall = "BLOCKED" if overall_blockers else "READY"

    return AssetReadinessResponse(
        asset_id=asset.id,
        overall_status=overall,
        dimensions=dimensions,
        evaluated_at=datetime.now(UTC),
        disclaimer=(
            "Operational & readiness decision context only; not an electronic Release to Service (RTS) signature."
        ),
    )


# ---------------------------------------------------------------------------
# Unified Domain History & Context
# ---------------------------------------------------------------------------

def get_asset_history(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, limit: int = 50
) -> AssetHistoryResponse:
    """Unified chronological domain timeline across audit events, flights, and installations."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)

    events: list[AssetHistoryEventResponse] = []

    # 1. Audit events for this asset
    audit_rows = db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == organization_id,
            AuditEvent.entity_type == "Asset",
            AuditEvent.entity_id == asset.id,
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).scalars().all()

    for a in audit_rows:
        events.append(
            AssetHistoryEventResponse(
                event_id=f"audit-{a.id}",
                event_type="AUDIT_EVENT",
                occurred_at=a.created_at,
                title=f"Administrative Action: {a.action}",
                description=f"Action '{a.action}' performed on asset {asset.registration or asset.id}.",
                actor=str(a.user_id) if a.user_id else None,
                entity_type="Asset",
                entity_id=str(asset.id),
                metadata=a.payload or {},
            )
        )

    # 2. Flight events
    flight_rows = db.execute(
        select(Flight)
        .where(Flight.asset_id == asset.id, Flight.organization_id == organization_id)
        .order_by(Flight.flown_at.desc())
        .limit(limit)
    ).scalars().all()

    for f in flight_rows:
        events.append(
            AssetHistoryEventResponse(
                event_id=f"flight-{f.id}",
                event_type="FLIGHT_SORTIE",
                occurred_at=f.flown_at,
                title=f"Flight Executed ({f.duration_minutes} min, {f.cycles} cyc)",
                description=f.notes or "Operational sector logged.",
                actor=str(f.pilot_user_id) if f.pilot_user_id else None,
                entity_type="Flight",
                entity_id=str(f.id),
                metadata={"duration_minutes": f.duration_minutes, "cycles": f.cycles},
            )
        )

    # 3. Component installations
    component_installs = db.execute(
        select(ComponentInstallation, Component)
        .join(Component, ComponentInstallation.component_id == Component.id)
        .where(
            ComponentInstallation.asset_id == asset.id,
            ComponentInstallation.organization_id == organization_id,
        )
        .order_by(ComponentInstallation.installed_at.desc())
        .limit(limit)
    ).all()

    for ci, c in component_installs:
        events.append(
            AssetHistoryEventResponse(
                event_id=f"comp-inst-{ci.id}",
                event_type="COMPONENT_INSTALLATION",
                occurred_at=ci.installed_at,
                title=f"Component Installed: {c.name} ({c.component_type})",
                description=f"Serial: {c.serial_number or 'N/A'}",
                actor=str(ci.installed_by) if ci.installed_by else None,
                entity_type="Component",
                entity_id=str(c.id),
                metadata={"component_type": c.component_type, "status": c.status},
            )
        )
        if ci.removed_at:
            events.append(
                AssetHistoryEventResponse(
                    event_id=f"comp-rem-{ci.id}",
                    event_type="COMPONENT_REMOVAL",
                    occurred_at=ci.removed_at,
                    title=f"Component Removed: {c.name}",
                    description=f"Removed from asset {asset.registration or asset.id}.",
                    actor=str(ci.removed_by) if ci.removed_by else None,
                    entity_type="Component",
                    entity_id=str(c.id),
                    metadata={"component_type": c.component_type},
                )
            )

    # Sort all events chronologically descending
    events.sort(key=lambda e: e.occurred_at, reverse=True)
    sliced_events = events[:limit]

    return AssetHistoryResponse(
        asset_id=asset.id,
        events=sliced_events,
        total=len(sliced_events),
    )


def get_asset_domain_context(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID
) -> AssetDomainContextResponse:
    """Comprehensive structured domain context aggregated for future intelligence systems."""
    asset = get_asset(db, organization_id=organization_id, asset_id=asset_id)
    configuration = get_asset_configuration(db, organization_id=organization_id, asset_id=asset_id)
    utilization = get_asset_utilization(db, organization_id=organization_id, asset_id=asset_id)
    readiness = get_asset_readiness(db, organization_id=organization_id, asset_id=asset_id)
    comp_data = get_asset_compliance(db, organization_id=organization_id, asset_id=asset_id)

    # Count open work orders
    open_wo_count = db.execute(
        select(func.count(WorkOrder.id)).where(
            WorkOrder.asset_id == asset.id,
            WorkOrder.organization_id == organization_id,
            WorkOrder.status != "COMPLETED",
            WorkOrder.deleted_at.is_(None),
        )
    ).scalar_one()

    # Count open findings
    open_findings_count = db.execute(
        select(func.count(Finding.id)).where(
            Finding.asset_id == asset.id,
            Finding.organization_id == organization_id,
            Finding.status != FindingStatus.CLOSED,
        )
    ).scalar_one()

    # Get last flight timestamp
    last_flight = db.execute(
        select(Flight.flown_at)
        .where(Flight.asset_id == asset.id, Flight.organization_id == organization_id)
        .order_by(Flight.flown_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    from app.schemas.asset import AssetComplianceResponse
    compliance = AssetComplianceResponse(
        asset_id=asset.id,
        assessments=comp_data["assessments"],
        overall_status=comp_data["overall_status"],
        compliant_count=comp_data["compliant_count"],
        non_compliant_count=comp_data["non_compliant_count"],
    )

    return AssetDomainContextResponse(
        identity=AssetResponse.model_validate(asset),
        operational_status=AssetOperationalStatus.READY.value if asset.status == AssetLifecycleStatus.ACTIVE.value else AssetOperationalStatus.GROUNDED.value,
        lifecycle_status=asset.status,
        readiness=readiness,
        configuration=configuration,
        utilization=utilization,
        compliance=compliance,
        open_work_orders_count=int(open_wo_count),
        open_findings_count=int(open_findings_count),
        overdue_maintenance_count=1 if readiness.dimensions[1].status == "BLOCKED" else 0,
        last_flight_at=last_flight,
    )
