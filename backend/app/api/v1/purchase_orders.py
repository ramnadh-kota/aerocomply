import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.purchase_order import (
    PurchaseOrderAcknowledgeRequest,
    PurchaseOrderCreateRequest,
    PurchaseOrderResponse,
)
from app.services import purchase_order_service

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


@router.post("", response_model=PurchaseOrderResponse, status_code=201)
def create_purchase_order(
    payload: PurchaseOrderCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.create_purchase_order(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        payload=payload,
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.get("", response_model=list[PurchaseOrderResponse])
def list_purchase_orders(
    status: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_READ)),
) -> list[PurchaseOrderResponse]:
    purchase_orders = purchase_order_service.list_purchase_orders(
        db, organization_id=current_user.organization_id, status=status
    )
    return [PurchaseOrderResponse.model_validate(po) for po in purchase_orders]


@router.get("/{po_id}", response_model=PurchaseOrderResponse)
def get_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_READ)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.get_purchase_order(
        db, organization_id=current_user.organization_id, purchase_order_id=po_id
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/{po_id}/submit-for-approval", response_model=PurchaseOrderResponse)
def submit_for_approval(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.submit_for_approval(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.id, po_id=po_id
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/{po_id}/approve", response_model=PurchaseOrderResponse)
def approve_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_APPROVE)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.approve_purchase_order(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.id, po_id=po_id
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/{po_id}/send", response_model=PurchaseOrderResponse)
def send_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.send_purchase_order(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.id, po_id=po_id
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/{po_id}/acknowledge", response_model=PurchaseOrderResponse)
def acknowledge_purchase_order(
    po_id: uuid.UUID,
    payload: PurchaseOrderAcknowledgeRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.acknowledge_purchase_order(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        po_id=po_id,
        payload=payload,
    )
    return PurchaseOrderResponse.model_validate(purchase_order)


@router.post("/{po_id}/cancel", response_model=PurchaseOrderResponse)
def cancel_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> PurchaseOrderResponse:
    purchase_order = purchase_order_service.cancel_purchase_order(
        db, organization_id=current_user.organization_id, actor_user_id=current_user.id, po_id=po_id
    )
    return PurchaseOrderResponse.model_validate(purchase_order)
