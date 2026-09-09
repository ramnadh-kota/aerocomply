import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.inventory_transaction import (
    InventoryAdjustRequest,
    InventoryConsumeRequest,
    InventoryReceiveRequest,
    InventoryReleaseRequest,
    InventoryReserveRequest,
    InventoryTransactionResponse,
)
from app.services import inventory_transaction_service

router = APIRouter(prefix="/parts/{part_id}/inventory", tags=["inventory"])


@router.post("/receive", response_model=InventoryTransactionResponse, status_code=201)
def receive(
    part_id: uuid.UUID,
    payload: InventoryReceiveRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> InventoryTransactionResponse:
    transaction = inventory_transaction_service.receive_part(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        payload=payload,
    )
    return InventoryTransactionResponse.model_validate(transaction)


@router.post("/reserve", response_model=InventoryTransactionResponse, status_code=201)
def reserve(
    part_id: uuid.UUID,
    payload: InventoryReserveRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> InventoryTransactionResponse:
    transaction = inventory_transaction_service.reserve_part(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        payload=payload,
    )
    return InventoryTransactionResponse.model_validate(transaction)


@router.post("/release", response_model=InventoryTransactionResponse, status_code=201)
def release(
    part_id: uuid.UUID,
    payload: InventoryReleaseRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> InventoryTransactionResponse:
    transaction = inventory_transaction_service.release_reservation(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        payload=payload,
    )
    return InventoryTransactionResponse.model_validate(transaction)


@router.post("/consume", response_model=InventoryTransactionResponse, status_code=201)
def consume(
    part_id: uuid.UUID,
    payload: InventoryConsumeRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> InventoryTransactionResponse:
    transaction = inventory_transaction_service.consume_part(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        payload=payload,
    )
    return InventoryTransactionResponse.model_validate(transaction)


@router.post("/adjust", response_model=InventoryTransactionResponse, status_code=201)
def adjust(
    part_id: uuid.UUID,
    payload: InventoryAdjustRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_WRITE)),
) -> InventoryTransactionResponse:
    transaction = inventory_transaction_service.adjust_part(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        part_id=part_id,
        payload=payload,
    )
    return InventoryTransactionResponse.model_validate(transaction)


@router.get("/transactions", response_model=list[InventoryTransactionResponse])
def list_transactions(
    part_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PART_READ)),
) -> list[InventoryTransactionResponse]:
    transactions = inventory_transaction_service.list_transactions_for_part(
        db, organization_id=current_user.organization_id, part_id=part_id
    )
    return [InventoryTransactionResponse.model_validate(t) for t in transactions]
