import uuid

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.purchase_order import PurchaseOrder, PurchaseOrderStatus
from app.schemas.inventory_transaction import InventoryReceiveRequest
from app.schemas.receiving import ReceivePurchaseOrderRequest
from app.services import inventory_transaction_service, procurement_service, purchase_order_service
from app.services.audit_service import record_audit_event

# States a PO must be in to accept a delivery. PARTIALLY_RECEIVED is included
# so a second, later shipment against the same PO can still be received.
_RECEIVABLE_STATUSES = {
    PurchaseOrderStatus.SENT,
    PurchaseOrderStatus.ACKNOWLEDGED,
    PurchaseOrderStatus.PARTIALLY_RECEIVED,
}


def receive_purchase_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    po_id: uuid.UUID,
    payload: ReceivePurchaseOrderRequest,
) -> PurchaseOrder:
    purchase_order = purchase_order_service.get_purchase_order(
        db, organization_id=organization_id, purchase_order_id=po_id
    )
    if purchase_order.status not in _RECEIVABLE_STATUSES:
        raise ConflictError(
            f"Cannot receive against a purchase order in status {purchase_order.status}",
            code="not_receivable",
        )

    lines_by_id = {line.id: line for line in purchase_order.lines}

    for line_receipt in payload.lines:
        line = lines_by_id.get(line_receipt.line_id)
        if line is None:
            raise ConflictError(
                f"Line {line_receipt.line_id} does not belong to this purchase order",
                code="line_not_found",
            )
        remaining = line.quantity - line.received_quantity
        if line_receipt.quantity > remaining:
            raise ConflictError(
                f"Cannot receive {line_receipt.quantity} against line {line.id}: "
                f"only {remaining} remain outstanding",
                code="over_receipt",
            )

        line.received_quantity += line_receipt.quantity
        db.add(line)

        # Only advances real inventory (via the M3.4 ledger, never duplicated
        # here) when this line traces to a ProcurementRequest with a known
        # Part — a PO line with only a free-text part_number has nothing to
        # post against and is recorded on the line only. A received part is
        # NOT automatically marked serviceable/available-for-issue beyond
        # what receive_part already does (on-hand increases; it still must
        # clear whatever inspection/cert workflow governs it before use —
        # no such gate exists in this codebase yet, so none is claimed here).
        if line.procurement_request_id is not None:
            request = procurement_service.get_request(
                db, organization_id=organization_id, request_id=line.procurement_request_id
            )
            if request.part_id is not None:
                inventory_transaction_service.receive_part(
                    db,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    part_id=request.part_id,
                    payload=InventoryReceiveRequest(
                        quantity=line_receipt.quantity,
                        reference_type="purchase_order_line",
                        reference_id=line.id,
                        notes=payload.notes,
                    ),
                )

    all_fulfilled = all(line.received_quantity >= line.quantity for line in purchase_order.lines)
    any_received = any(line.received_quantity > 0 for line in purchase_order.lines)
    previous_status = purchase_order.status
    purchase_order.status = (
        PurchaseOrderStatus.RECEIVED
        if all_fulfilled
        else PurchaseOrderStatus.PARTIALLY_RECEIVED
        if any_received
        else purchase_order.status
    )
    db.add(purchase_order)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="purchase_order.received",
        entity_type="PurchaseOrder",
        entity_id=purchase_order.id,
        metadata={
            "from_status": previous_status,
            "to_status": purchase_order.status,
            "lines_received": [
                {"line_id": str(lr.line_id), "quantity": lr.quantity} for lr in payload.lines
            ],
        },
    )

    if purchase_order.status == PurchaseOrderStatus.RECEIVED:
        for line in purchase_order.lines:
            if line.procurement_request_id is not None:
                request = procurement_service.get_request(
                    db, organization_id=organization_id, request_id=line.procurement_request_id
                )
                if request.status == "ORDERED":
                    procurement_service.mark_received(
                        db,
                        organization_id=organization_id,
                        actor_user_id=actor_user_id,
                        request_id=request.id,
                    )

    db.commit()
    db.refresh(purchase_order)
    return purchase_order
