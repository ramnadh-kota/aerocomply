"""Phase 18.6: tenant-scoped Drone Operations API. Drone identity is Asset
(asset_type=DRONE) -- see app/services/drone_service.py's module docstring.
All routes gated by the existing Permission.DRONE_READ/DRONE_WRITE, never a
new permission per sub-resource."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.drone_ops import (
    AssetLifecycleEventResponse,
    AssetLifecycleHistoryResponse,
    BatteryCreateRequest,
    BatteryInstallationListResponse,
    BatteryInstallationResponse,
    BatteryResponse,
    BatteryUpdateRequest,
    ComponentCreateRequest,
    ComponentInstallationListResponse,
    ComponentInstallationResponse,
    ComponentResponse,
    DeploymentReadinessResponse,
    DroneCreateRequest,
    DroneResponse,
    DroneUpdateRequest,
    FlightCreateRequest,
    FlightListResponse,
    FlightResponse,
    UtilizationResponse,
)
from app.schemas.maintenance_requirement import (
    AssetMaintenanceAccomplishmentCreateRequest,
    MaintenanceAccomplishmentResponse,
    MaintenanceDueItem,
    MaintenanceRequirementResponse,
)
from app.services import (
    battery_service,
    component_service,
    drone_service,
    flight_service,
    installation_service,
    maintenance_service,
    readiness_service,
)

router = APIRouter(tags=["drones"])


@router.get("/drones", response_model=list[DroneResponse])
def list_drones(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
    _entitled: CurrentUser = Depends(require_feature("drone_fleet_management")),
) -> list[DroneResponse]:
    drones = drone_service.list_drones(db, organization_id=current_user.organization_id)
    return [DroneResponse.model_validate(d) for d in drones]


@router.post("/drones", response_model=DroneResponse, status_code=201)
def create_drone(
    payload: DroneCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> DroneResponse:
    drone = drone_service.create_drone(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        registration=payload.registration,
        manufacturer=payload.manufacturer,
        model=payload.model,
        serial_number=payload.serial_number,
        facility_id=payload.facility_id,
    )
    return DroneResponse.model_validate(drone)


@router.get("/drones/{asset_id}", response_model=DroneResponse)
def get_drone(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
    _entitled: CurrentUser = Depends(require_feature("drone_fleet_management")),
) -> DroneResponse:
    drone = drone_service.get_drone(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return DroneResponse.model_validate(drone)


@router.patch("/drones/{asset_id}", response_model=DroneResponse)
def update_drone(
    asset_id: uuid.UUID,
    payload: DroneUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> DroneResponse:
    drone = drone_service.update_drone(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        manufacturer=payload.manufacturer,
        model=payload.model,
        status=payload.status,
        facility_id=payload.facility_id,
    )
    return DroneResponse.model_validate(drone)


@router.get("/drones/{asset_id}/batteries", response_model=list[BatteryResponse])
def list_batteries(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> list[BatteryResponse]:
    batteries = battery_service.list_batteries_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return [BatteryResponse.model_validate(b) for b in batteries]


@router.post("/drones/{asset_id}/batteries", response_model=BatteryResponse, status_code=201)
def attach_battery(
    asset_id: uuid.UUID,
    payload: BatteryCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> BatteryResponse:
    battery = battery_service.attach_battery(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        serial_number=payload.serial_number,
        manufacturer=payload.manufacturer,
        model=payload.model,
        capacity_mah=payload.capacity_mah,
        voltage=payload.voltage,
    )
    return BatteryResponse.model_validate(battery)


@router.patch("/batteries/{battery_id}", response_model=BatteryResponse)
def update_battery(
    battery_id: uuid.UUID,
    payload: BatteryUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> BatteryResponse:
    battery = battery_service.update_battery(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        battery_id=battery_id,
        health_percent=payload.health_percent,
        status=payload.status,
        notes=payload.notes,
    )
    return BatteryResponse.model_validate(battery)


@router.get("/drones/{asset_id}/components", response_model=list[ComponentResponse])
def list_components(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> list[ComponentResponse]:
    components = component_service.list_components_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return [ComponentResponse.model_validate(c) for c in components]


@router.post("/drones/{asset_id}/components", response_model=ComponentResponse, status_code=201)
def attach_component(
    asset_id: uuid.UUID,
    payload: ComponentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> ComponentResponse:
    component = component_service.attach_component(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        component_type=payload.component_type,
        name=payload.name,
        serial_number=payload.serial_number,
        manufacturer=payload.manufacturer,
        model=payload.model,
    )
    return ComponentResponse.model_validate(component)


@router.get("/drones/{asset_id}/flights", response_model=FlightListResponse)
def list_flights(
    asset_id: uuid.UUID,
    limit: int = Query(default=flight_service.FLIGHT_HISTORY_DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> FlightListResponse:
    flights, total = flight_service.list_flights_for_asset(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        limit=limit,
        offset=offset,
    )
    effective_limit = max(1, min(limit, flight_service.FLIGHT_HISTORY_MAX_LIMIT))
    return FlightListResponse(
        items=[FlightResponse.model_validate(f) for f in flights],
        total=total,
        limit=effective_limit,
        offset=max(0, offset),
    )


@router.get("/flights/{flight_id}", response_model=FlightResponse)
def get_flight(
    flight_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> FlightResponse:
    flight = flight_service.get_flight(
        db, organization_id=current_user.organization_id, flight_id=flight_id
    )
    return FlightResponse.model_validate(flight)


@router.post("/drones/{asset_id}/flights", response_model=FlightResponse, status_code=201)
def record_flight(
    asset_id: uuid.UUID,
    payload: FlightCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> FlightResponse:
    flight = flight_service.record_flight(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        asset_id=asset_id,
        flown_at=payload.flown_at,
        duration_minutes=payload.duration_minutes,
        cycles=payload.cycles,
        pilot_user_id=payload.pilot_user_id,
        notes=payload.notes,
    )
    return FlightResponse.model_validate(flight)


@router.get("/drones/{asset_id}/utilization", response_model=UtilizationResponse)
def get_utilization(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> UtilizationResponse:
    utilization = flight_service.get_utilization(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return UtilizationResponse(asset_id=asset_id, **utilization)


@router.get("/drones/{asset_id}/deployment-readiness", response_model=DeploymentReadinessResponse)
def get_deployment_readiness(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> DeploymentReadinessResponse:
    result = readiness_service.evaluate_deployment_readiness(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return DeploymentReadinessResponse(**result)


# ---------------------------------------------------------------------------
# M17.2B: battery/component lifecycle read APIs. Same Permission.DRONE_READ
# gate as every other read route in this file (no new permission -- see
# module docstring); reuses app.services.installation_service, which is
# itself unchanged in its write semantics (install/remove) from M17.2A.
# Read-only: none of these routes mutate Battery.asset_id/Component.asset_id
# or the *_installations tables.
# ---------------------------------------------------------------------------


@router.get("/batteries/{battery_id}", response_model=BatteryResponse)
def get_battery(
    battery_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> BatteryResponse:
    battery = battery_service.get_battery(
        db, organization_id=current_user.organization_id, battery_id=battery_id
    )
    return BatteryResponse.model_validate(battery)


@router.get("/batteries/{battery_id}/history", response_model=BatteryInstallationListResponse)
def get_battery_history(
    battery_id: uuid.UUID,
    limit: int = Query(default=installation_service.LIFECYCLE_HISTORY_DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> BatteryInstallationListResponse:
    # Confirms the battery belongs to this tenant before returning any
    # history for it (cross-tenant IDOR/enumeration otherwise).
    battery_service.get_battery(
        db, organization_id=current_user.organization_id, battery_id=battery_id
    )
    items, total = installation_service.list_battery_history(
        db, organization_id=current_user.organization_id, battery_id=battery_id,
        limit=limit, offset=offset,
    )
    effective_limit = max(1, min(limit, installation_service.LIFECYCLE_HISTORY_MAX_LIMIT))
    return BatteryInstallationListResponse(
        items=[BatteryInstallationResponse.model_validate(i) for i in items],
        total=total,
        limit=effective_limit,
        offset=max(0, offset),
    )


@router.get("/components/{component_id}", response_model=ComponentResponse)
def get_component(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> ComponentResponse:
    component = component_service.get_component(
        db, organization_id=current_user.organization_id, component_id=component_id
    )
    return ComponentResponse.model_validate(component)


@router.get(
    "/components/{component_id}/history", response_model=ComponentInstallationListResponse
)
def get_component_history(
    component_id: uuid.UUID,
    limit: int = Query(default=installation_service.LIFECYCLE_HISTORY_DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> ComponentInstallationListResponse:
    component_service.get_component(
        db, organization_id=current_user.organization_id, component_id=component_id
    )
    items, total = installation_service.list_component_history(
        db, organization_id=current_user.organization_id, component_id=component_id,
        limit=limit, offset=offset,
    )
    effective_limit = max(1, min(limit, installation_service.LIFECYCLE_HISTORY_MAX_LIMIT))
    return ComponentInstallationListResponse(
        items=[ComponentInstallationResponse.model_validate(i) for i in items],
        total=total,
        limit=effective_limit,
        offset=max(0, offset),
    )


@router.get("/drones/{asset_id}/lifecycle-history", response_model=AssetLifecycleHistoryResponse)
def get_asset_lifecycle_history(
    asset_id: uuid.UUID,
    limit: int = Query(default=installation_service.LIFECYCLE_HISTORY_DEFAULT_LIMIT, ge=1),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> AssetLifecycleHistoryResponse:
    events, total = installation_service.list_asset_lifecycle_history(
        db, organization_id=current_user.organization_id, asset_id=asset_id,
        limit=limit, offset=offset,
    )
    effective_limit = max(1, min(limit, installation_service.LIFECYCLE_HISTORY_MAX_LIMIT))
    return AssetLifecycleHistoryResponse(
        items=[AssetLifecycleEventResponse.model_validate(e) for e in events],
        total=total,
        limit=effective_limit,
        offset=max(0, offset),
    )


# ---------------------------------------------------------------------------
# M17.4A/B: usage-based maintenance for a drone. Extends the existing
# MaintenanceRequirement/MaintenanceRequirementApplicability/
# MaintenanceAccomplishment architecture (app/services/maintenance_service.py,
# originally aircraft-only) rather than duplicating it -- these routes are
# the asset(Drone)-scoped counterparts of the existing aircraft
# applicability/accomplishment endpoints in app/api/v1/maintenance.py.
# Same Permission.DRONE_READ/DRONE_WRITE gate as every other route here.
# ---------------------------------------------------------------------------


@router.post(
    "/drones/{asset_id}/maintenance-requirements/{requirement_id}/applicability",
    response_model=MaintenanceRequirementResponse,
    status_code=201,
)
def add_maintenance_applicability(
    asset_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MaintenanceRequirementResponse:
    requirement = maintenance_service.add_applicability_for_asset(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        asset_id=asset_id,
    )
    return MaintenanceRequirementResponse.model_validate(requirement)


@router.post(
    "/drones/{asset_id}/maintenance-requirements/{requirement_id}/accomplishments",
    response_model=MaintenanceAccomplishmentResponse,
    status_code=201,
)
def record_maintenance_accomplishment(
    asset_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: AssetMaintenanceAccomplishmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MaintenanceAccomplishmentResponse:
    accomplishment = maintenance_service.record_accomplishment_for_asset(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        asset_id=asset_id,
        payload=payload,
    )
    return MaintenanceAccomplishmentResponse.model_validate(accomplishment)


@router.get("/drones/{asset_id}/maintenance-due", response_model=list[MaintenanceDueItem])
def get_maintenance_due(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> list[MaintenanceDueItem]:
    return maintenance_service.get_maintenance_due_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


# ---------------------------------------------------------------------------
# M17.5A/B: usage-based maintenance for a serialized Battery/Component,
# reusing the exact same MaintenanceRequirement architecture and
# Permission.DRONE_READ/DRONE_WRITE gate as the asset(Drone)-level routes
# above -- no new permission, no second maintenance system.
# ---------------------------------------------------------------------------


@router.post(
    "/batteries/{battery_id}/maintenance-requirements/{requirement_id}/applicability",
    response_model=MaintenanceRequirementResponse,
    status_code=201,
)
def add_battery_maintenance_applicability(
    battery_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MaintenanceRequirementResponse:
    requirement = maintenance_service.add_applicability_for_battery(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        battery_id=battery_id,
    )
    return MaintenanceRequirementResponse.model_validate(requirement)


@router.post(
    "/batteries/{battery_id}/maintenance-requirements/{requirement_id}/accomplishments",
    response_model=MaintenanceAccomplishmentResponse,
    status_code=201,
)
def record_battery_maintenance_accomplishment(
    battery_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: AssetMaintenanceAccomplishmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MaintenanceAccomplishmentResponse:
    accomplishment = maintenance_service.record_accomplishment_for_battery(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        battery_id=battery_id,
        payload=payload,
    )
    return MaintenanceAccomplishmentResponse.model_validate(accomplishment)


@router.get("/batteries/{battery_id}/maintenance-due", response_model=list[MaintenanceDueItem])
def get_battery_maintenance_due(
    battery_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> list[MaintenanceDueItem]:
    return maintenance_service.get_maintenance_due_for_battery(
        db, organization_id=current_user.organization_id, battery_id=battery_id
    )


@router.post(
    "/components/{component_id}/maintenance-requirements/{requirement_id}/applicability",
    response_model=MaintenanceRequirementResponse,
    status_code=201,
)
def add_component_maintenance_applicability(
    component_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MaintenanceRequirementResponse:
    requirement = maintenance_service.add_applicability_for_component(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        component_id=component_id,
    )
    return MaintenanceRequirementResponse.model_validate(requirement)


@router.post(
    "/components/{component_id}/maintenance-requirements/{requirement_id}/accomplishments",
    response_model=MaintenanceAccomplishmentResponse,
    status_code=201,
)
def record_component_maintenance_accomplishment(
    component_id: uuid.UUID,
    requirement_id: uuid.UUID,
    payload: AssetMaintenanceAccomplishmentCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_WRITE)),
) -> MaintenanceAccomplishmentResponse:
    accomplishment = maintenance_service.record_accomplishment_for_component(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        requirement_id=requirement_id,
        component_id=component_id,
        payload=payload,
    )
    return MaintenanceAccomplishmentResponse.model_validate(accomplishment)


@router.get(
    "/components/{component_id}/maintenance-due", response_model=list[MaintenanceDueItem]
)
def get_component_maintenance_due(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> list[MaintenanceDueItem]:
    return maintenance_service.get_maintenance_due_for_component(
        db, organization_id=current_user.organization_id, component_id=component_id
    )
