"""Helicopter (/helicopters) and eVTOL/AAM (/evtols) fleet APIs.

Each family is gated at the ROUTER boundary by its own suite feature (helicopter_fleet_management /
evtol_fleet_management), so a tenant without that suite gets SUITE_ENTITLEMENT_REQUIRED for every sub-route. Identity is
Asset (asset_type HELICOPTER / EVTOL) + a 1:1 detail row; flights, utilization, components, batteries and maintenance
reuse the shared services, which are told the asset type so a route can only ever see its own family.
RBAC uses the aircraft-class permissions (AIRCRAFT_READ / AIRCRAFT_WRITE) plus HUMS_WRITE for sensor setup."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.drone_ops import (
    AssetLifecycleEventResponse,
    AssetLifecycleHistoryResponse,
    BatteryCreateRequest,
    BatteryResponse,
    ComponentCreateRequest,
    ComponentResponse,
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
    airframe_service,
    battery_service,
    component_service,
    drone_service,
    flight_service,
    hums_templates,
    installation_service,
    maintenance_service,
)


class AirframeCreate(BaseModel):
    registration: str = Field(min_length=1, max_length=16)
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    serial_number: str | None = Field(default=None, max_length=128)
    facility_id: uuid.UUID | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class AirframeUpdate(BaseModel):
    manufacturer: str | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)
    facility_id: uuid.UUID | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


_DETAIL_KEYS = {
    "HELICOPTER": ("rotor_system", "main_rotor_blade_count", "engine_count", "max_takeoff_weight_kg"),
    "EVTOL": ("configuration", "propulsor_count", "battery_nominal_energy_kwh", "hv_bus_nominal_voltage_v",
              "max_takeoff_weight_kg", "passenger_capacity"),
}


def _view(asset_type: str, asset, row) -> dict[str, Any]:
    return {
        "id": str(asset.id), "organization_id": str(asset.organization_id), "asset_type": asset.asset_type,
        "registration": asset.registration, "manufacturer": asset.manufacturer, "model": asset.model,
        "serial_number": asset.serial_number, "status": asset.status,
        "facility_id": str(asset.facility_id) if asset.facility_id else None,
        "detail": {k: getattr(row, k, None) for k in _DETAIL_KEYS[asset_type]} if row is not None else {},
    }


def _422(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


def build_router(*, prefix: str, asset_type: str, feature: str, tag: str, with_batteries: bool) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag], dependencies=[Depends(require_feature(feature))])
    READ = Permission.AIRCRAFT_READ
    WRITE = Permission.AIRCRAFT_WRITE

    def _airframe(db: Session, user: CurrentUser, asset_id: uuid.UUID):
        return drone_service.get_airframe(db, organization_id=user.organization_id, asset_id=asset_id,
                                          asset_type=asset_type)

    @router.get("")
    def list_(db: Session = Depends(get_db_session), user: CurrentUser = Depends(require_permission(READ))) -> list[dict]:
        rows = airframe_service.list_airframes(db, asset_type=asset_type, organization_id=user.organization_id)
        return [_view(asset_type, a, d) for a, d in rows]

    @router.post("", status_code=201)
    def create(payload: AirframeCreate, db: Session = Depends(get_db_session),
               user: CurrentUser = Depends(require_permission(WRITE))) -> dict:
        try:
            a, d = airframe_service.create_airframe(
                db, asset_type=asset_type, organization_id=user.organization_id, actor_user_id=user.id,
                registration=payload.registration, manufacturer=payload.manufacturer, model=payload.model,
                serial_number=payload.serial_number, facility_id=payload.facility_id, detail=payload.detail)
        except airframe_service.AirframeValidationError as exc:
            raise _422(exc) from exc
        return _view(asset_type, a, d)

    @router.get("/{asset_id}")
    def get(asset_id: uuid.UUID, db: Session = Depends(get_db_session),
            user: CurrentUser = Depends(require_permission(READ))) -> dict:
        a, d = airframe_service.get_airframe(db, asset_type=asset_type, organization_id=user.organization_id,
                                             asset_id=asset_id)
        return _view(asset_type, a, d)

    @router.patch("/{asset_id}")
    def update(asset_id: uuid.UUID, payload: AirframeUpdate, db: Session = Depends(get_db_session),
               user: CurrentUser = Depends(require_permission(WRITE))) -> dict:
        try:
            a, d = airframe_service.update_airframe(
                db, asset_type=asset_type, organization_id=user.organization_id, actor_user_id=user.id,
                asset_id=asset_id, manufacturer=payload.manufacturer, model=payload.model, status=payload.status,
                facility_id=payload.facility_id, detail=payload.detail)
        except airframe_service.AirframeValidationError as exc:
            raise _422(exc) from exc
        return _view(asset_type, a, d)

    # ---- components -------------------------------------------------------------------------------
    @router.get("/{asset_id}/components", response_model=list[ComponentResponse])
    def list_components(asset_id: uuid.UUID, db: Session = Depends(get_db_session),
                        user: CurrentUser = Depends(require_permission(READ))):
        return [ComponentResponse.model_validate(c) for c in component_service.list_components_for_asset(
            db, organization_id=user.organization_id, asset_id=asset_id, asset_type=asset_type)]

    @router.post("/{asset_id}/components", response_model=ComponentResponse, status_code=201)
    def attach_component(asset_id: uuid.UUID, payload: ComponentCreateRequest, db: Session = Depends(get_db_session),
                         user: CurrentUser = Depends(require_permission(WRITE))):
        c = component_service.attach_component(
            db, organization_id=user.organization_id, actor_user_id=user.id, asset_id=asset_id,
            asset_type=asset_type, component_type=payload.component_type, name=payload.name,
            serial_number=payload.serial_number, manufacturer=payload.manufacturer, model=payload.model)
        return ComponentResponse.model_validate(c)

    # ---- flights / utilization (flight hours and cycles) --------------------------------------------
    @router.get("/{asset_id}/flights", response_model=FlightListResponse)
    def list_flights(asset_id: uuid.UUID, limit: int = Query(default=flight_service.FLIGHT_HISTORY_DEFAULT_LIMIT, ge=1),
                     offset: int = Query(default=0, ge=0), db: Session = Depends(get_db_session),
                     user: CurrentUser = Depends(require_permission(READ))):
        _airframe(db, user, asset_id)
        flights, total = flight_service.list_flights_for_asset(
            db, organization_id=user.organization_id, asset_id=asset_id, limit=limit, offset=offset)
        return FlightListResponse(items=[FlightResponse.model_validate(f) for f in flights], total=total,
                                  limit=max(1, min(limit, flight_service.FLIGHT_HISTORY_MAX_LIMIT)),
                                  offset=max(0, offset))

    @router.post("/{asset_id}/flights", response_model=FlightResponse, status_code=201)
    def record_flight(asset_id: uuid.UUID, payload: FlightCreateRequest, db: Session = Depends(get_db_session),
                      user: CurrentUser = Depends(require_permission(WRITE))):
        _airframe(db, user, asset_id)
        f = flight_service.record_flight(
            db, organization_id=user.organization_id, actor_user_id=user.id, asset_id=asset_id,
            flown_at=payload.flown_at, duration_minutes=payload.duration_minutes, cycles=payload.cycles,
            pilot_user_id=payload.pilot_user_id, notes=payload.notes, mission_id=payload.mission_id,
            flight_number=payload.flight_number, origin=payload.origin, destination=payload.destination,
            departure_time=payload.departure_time, arrival_time=payload.arrival_time,
            mission_type=payload.mission_type, status=payload.status)
        return FlightResponse.model_validate(f)

    @router.get("/{asset_id}/utilization", response_model=UtilizationResponse)
    def utilization(asset_id: uuid.UUID, db: Session = Depends(get_db_session),
                    user: CurrentUser = Depends(require_permission(READ))):
        _airframe(db, user, asset_id)
        return UtilizationResponse(asset_id=asset_id, **flight_service.get_utilization(
            db, organization_id=user.organization_id, asset_id=asset_id))

    # ---- maintenance ---------------------------------------------------------------------------------
    @router.get("/{asset_id}/maintenance-due", response_model=list[MaintenanceDueItem])
    def maintenance_due(asset_id: uuid.UUID, db: Session = Depends(get_db_session),
                        user: CurrentUser = Depends(require_permission(READ))):
        return maintenance_service.get_maintenance_due_for_asset(
            db, organization_id=user.organization_id, asset_id=asset_id, asset_type=asset_type)

    @router.post("/{asset_id}/maintenance-requirements/{requirement_id}/applicability",
                 response_model=MaintenanceRequirementResponse, status_code=201)
    def add_applicability(asset_id: uuid.UUID, requirement_id: uuid.UUID, db: Session = Depends(get_db_session),
                          user: CurrentUser = Depends(require_permission(WRITE))):
        return MaintenanceRequirementResponse.model_validate(maintenance_service.add_applicability_for_asset(
            db, organization_id=user.organization_id, actor_user_id=user.id, requirement_id=requirement_id,
            asset_id=asset_id, asset_type=asset_type))

    @router.post("/{asset_id}/maintenance-requirements/{requirement_id}/accomplishments",
                 response_model=MaintenanceAccomplishmentResponse, status_code=201)
    def record_accomplishment(asset_id: uuid.UUID, requirement_id: uuid.UUID,
                              payload: AssetMaintenanceAccomplishmentCreateRequest,
                              db: Session = Depends(get_db_session),
                              user: CurrentUser = Depends(require_permission(WRITE))):
        return MaintenanceAccomplishmentResponse.model_validate(maintenance_service.record_accomplishment_for_asset(
            db, organization_id=user.organization_id, actor_user_id=user.id, requirement_id=requirement_id,
            asset_id=asset_id, payload=payload, asset_type=asset_type))

    @router.get("/{asset_id}/lifecycle-history", response_model=AssetLifecycleHistoryResponse)
    def lifecycle_history(asset_id: uuid.UUID,
                          limit: int = Query(default=installation_service.LIFECYCLE_HISTORY_DEFAULT_LIMIT, ge=1),
                          offset: int = Query(default=0, ge=0), db: Session = Depends(get_db_session),
                          user: CurrentUser = Depends(require_permission(READ))):
        events, total = installation_service.list_asset_lifecycle_history(
            db, organization_id=user.organization_id, asset_id=asset_id, asset_type=asset_type,
            limit=limit, offset=offset)
        return AssetLifecycleHistoryResponse(
            items=[AssetLifecycleEventResponse.model_validate(e) for e in events], total=total,
            limit=max(1, min(limit, installation_service.LIFECYCLE_HISTORY_MAX_LIMIT)),
            offset=max(0, offset))

    # ---- HUMS starter sensors --------------------------------------------------------------------------
    @router.post("/{asset_id}/hums/apply-template", dependencies=[Depends(require_feature("hums"))])
    def apply_hums_template(asset_id: uuid.UUID, db: Session = Depends(get_db_session),
                            user: CurrentUser = Depends(require_permission(Permission.HUMS_WRITE))) -> dict:
        asset = _airframe(db, user, asset_id)
        out = hums_templates.apply_template(db, organization_id=user.organization_id, user_id=user.id, asset=asset)
        db.commit()
        return out

    # ---- eVTOL high-voltage batteries ---------------------------------------------------------------------
    if with_batteries:
        @router.get("/{asset_id}/batteries", response_model=list[BatteryResponse],
                    dependencies=[Depends(require_feature("battery_analytics"))])
        def list_batteries(asset_id: uuid.UUID, db: Session = Depends(get_db_session),
                           user: CurrentUser = Depends(require_permission(READ))):
            return [BatteryResponse.model_validate(b) for b in battery_service.list_batteries_for_asset(
                db, organization_id=user.organization_id, asset_id=asset_id, asset_type=asset_type)]

        @router.post("/{asset_id}/batteries", response_model=BatteryResponse, status_code=201,
                     dependencies=[Depends(require_feature("battery_analytics"))])
        def attach_battery(asset_id: uuid.UUID, payload: BatteryCreateRequest, db: Session = Depends(get_db_session),
                           user: CurrentUser = Depends(require_permission(WRITE))):
            return BatteryResponse.model_validate(battery_service.attach_battery(
                db, organization_id=user.organization_id, actor_user_id=user.id, asset_id=asset_id,
                asset_type=asset_type, serial_number=payload.serial_number, manufacturer=payload.manufacturer,
                model=payload.model, capacity_mah=payload.capacity_mah, voltage=payload.voltage))

    return router


helicopters_router = build_router(prefix="/helicopters", asset_type="HELICOPTER",
                                  feature="helicopter_fleet_management", tag="helicopters", with_batteries=False)
evtols_router = build_router(prefix="/evtols", asset_type="EVTOL", feature="evtol_fleet_management",
                             tag="evtol", with_batteries=True)
