"""Phase 18.6: tenant-scoped Drone Operations API. Drone identity is Asset
(asset_type=DRONE) -- see app/services/drone_service.py's module docstring.
All routes gated by the existing Permission.DRONE_READ/DRONE_WRITE, never a
new permission per sub-resource."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.drone_ops import (
    BatteryCreateRequest,
    BatteryResponse,
    BatteryUpdateRequest,
    ComponentCreateRequest,
    ComponentResponse,
    DeploymentReadinessResponse,
    DroneCreateRequest,
    DroneResponse,
    DroneUpdateRequest,
    FlightCreateRequest,
    FlightResponse,
    UtilizationResponse,
)
from app.services import (
    battery_service,
    component_service,
    drone_service,
    flight_service,
    readiness_service,
)

router = APIRouter(tags=["drones"])


@router.get("/drones", response_model=list[DroneResponse])
def list_drones(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
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


@router.get("/drones/{asset_id}/flights", response_model=list[FlightResponse])
def list_flights(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.DRONE_READ)),
) -> list[FlightResponse]:
    flights = flight_service.list_flights_for_asset(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
    return [FlightResponse.model_validate(f) for f in flights]


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
