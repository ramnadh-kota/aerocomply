import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.purchase_order import PurchaseOrderResponse
from app.schemas.receiving import ReceivePurchaseOrderRequest
from app.services import receiving_service

router = APIRouter(prefix="/purchase-orders", tags=["receiving"])


@router.post("/{po_id}/receive", response_model=PurchaseOrderResponse)
def receive_purchase_order(
    po_id: uuid.UUID,
    payload: ReceivePurchaseOrderRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.PROCUREMENT_WRITE)),
) -> PurchaseOrderResponse:
    purchase_order = receiving_service.receive_purchase_order(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        po_id=po_id,
        payload=payload,
    )
    return PurchaseOrderResponse.model_validate(purchase_order)
