import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.part import PartResponse
from app.schemas.warehouse import (
    LocationCreateRequest,
    LocationResponse,
    PartLocationAssignRequest,
    WarehouseCreateRequest,
    WarehouseResponse,
)
from app.services import part_service, warehouse_service

router = APIRouter(tags=["warehouses"])


@router.post("/warehouses", response_model=WarehouseResponse, status_code=201)
def create_warehouse(
    payload: WarehouseCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> WarehouseResponse:
    warehouse = warehouse_service.create_warehouse(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return WarehouseResponse.model_validate(warehouse)


@router.get("/warehouses", response_model=list[WarehouseResponse])
def list_warehouses(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> list[WarehouseResponse]:
    warehouses = warehouse_service.list_warehouses(
        db, organization_id=current_user.organization_id
    )
    return [WarehouseResponse.model_validate(w) for w in warehouses]


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
def get_warehouse(
    warehouse_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> WarehouseResponse:
    warehouse = warehouse_service.get_warehouse(
        db, organization_id=current_user.organization_id, warehouse_id=warehouse_id
    )
    return WarehouseResponse.model_validate(warehouse)


@router.post(
    "/warehouses/{warehouse_id}/locations", response_model=LocationResponse, status_code=201
)
def create_location(
    warehouse_id: uuid.UUID,
    payload: LocationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> LocationResponse:
    location = warehouse_service.create_location(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        warehouse_id=warehouse_id,
        payload=payload,
    )
    return LocationResponse.model_validate(location)


@router.get("/warehouses/{warehouse_id}/locations", response_model=list[LocationResponse])
def list_locations(
    warehouse_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> list[LocationResponse]:
    locations = warehouse_service.list_locations_for_warehouse(
        db, organization_id=current_user.organization_id, warehouse_id=warehouse_id
    )
    return [LocationResponse.model_validate(loc) for loc in locations]


@router.post("/parts/{part_id}/location", response_model=PartResponse)
def assign_part_location(
    part_id: uuid.UUID,
    payload: PartLocationAssignRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> PartResponse:
    part = part_service.assign_location(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        location_id=payload.location_id,
    )
    return PartResponse.model_validate(part)
