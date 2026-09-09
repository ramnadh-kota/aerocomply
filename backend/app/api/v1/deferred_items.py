import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.deferred_item import (
    DeferredItemCloseRequest,
    DeferredItemCreateRequest,
    DeferredItemResponse,
    DeferredItemUpdateRequest,
)
from app.services import deferred_item_service

router = APIRouter(tags=["deferred-items"])


@router.post("/deferred-items", response_model=DeferredItemResponse, status_code=201)
def create_deferred_item(
    payload: DeferredItemCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> DeferredItemResponse:
    item = deferred_item_service.create_deferred_item(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return DeferredItemResponse.model_validate(item)


@router.get("/deferred-items/{item_id}", response_model=DeferredItemResponse)
def get_deferred_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> DeferredItemResponse:
    item = deferred_item_service.get_deferred_item(
        db, organization_id=current_user.organization_id, item_id=item_id
    )
    return DeferredItemResponse.model_validate(item)


@router.patch("/deferred-items/{item_id}", response_model=DeferredItemResponse)
def update_deferred_item(
    item_id: uuid.UUID,
    payload: DeferredItemUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> DeferredItemResponse:
    item = deferred_item_service.update_deferred_item(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        item_id=item_id,
        payload=payload,
    )
    return DeferredItemResponse.model_validate(item)


@router.post("/deferred-items/{item_id}/close", response_model=DeferredItemResponse)
def close_deferred_item(
    item_id: uuid.UUID,
    payload: DeferredItemCloseRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> DeferredItemResponse:
    item = deferred_item_service.close_deferred_item(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        item_id=item_id,
        payload=payload,
    )
    return DeferredItemResponse.model_validate(item)


@router.get("/aircraft/{aircraft_id}/deferred-items", response_model=list[DeferredItemResponse])
def list_deferred_items_for_aircraft(
    aircraft_id: uuid.UUID,
    open_only: bool = False,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[DeferredItemResponse]:
    items = deferred_item_service.list_deferred_items_for_aircraft(
        db,
        organization_id=current_user.organization_id,
        aircraft_id=aircraft_id,
        open_only=open_only,
    )
    return [DeferredItemResponse.model_validate(i) for i in items]


@router.get("/fleet/deferred-items", response_model=list[DeferredItemResponse])
def list_fleet_deferred_items(
    open_only: bool = False,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[DeferredItemResponse]:
    items = deferred_item_service.list_fleet_deferred_items(
        db, organization_id=current_user.organization_id, open_only=open_only
    )
    return [DeferredItemResponse.model_validate(i) for i in items]
