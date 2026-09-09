import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models.procurement_request import ProcurementRequestStatus
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus
from app.schemas.purchase_order import (
    PurchaseOrderAcknowledgeRequest,
    PurchaseOrderCreateRequest,
)
from app.services import procurement_service, vendor_service
from app.services.audit_service import record_audit_event

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    PurchaseOrderStatus.DRAFT: {
        PurchaseOrderStatus.PENDING_APPROVAL,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.PENDING_APPROVAL: {
        PurchaseOrderStatus.APPROVED,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.APPROVED: {
        PurchaseOrderStatus.SENT,
        PurchaseOrderStatus.CANCELLED,
    },
    PurchaseOrderStatus.SENT: {
        PurchaseOrderStatus.ACKNOWLEDGED,
        PurchaseOrderStatus.CANCELLED,
    },
    # ACKNOWLEDGED -> PARTIALLY_RECEIVED/RECEIVED is the receiving workflow's
    # responsibility (M3.8, not yet built), not this table.
}


def _require_transition(current: str, target: str) -> None:
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ConflictError(
            f"Cannot transition purchase order from {current} to {target}",
            code="invalid_transition",
        )


def _compute_totals(
    lines: list[PurchaseOrderLine], *, tax_cents: int | None, shipping_cents: int | None
) -> tuple[int, int]:
    subtotal = sum(
        line.quantity * line.unit_price_cents
        for line in lines
        if line.unit_price_cents is not None
    )
    total = subtotal + (tax_cents or 0) + (shipping_cents or 0)
    return subtotal, total


def create_purchase_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    payload: PurchaseOrderCreateRequest,
) -> PurchaseOrder:
    vendor_service.get_vendor(db, organization_id=organization_id, vendor_id=payload.vendor_id)

    linked_requests = []
    for line_payload in payload.lines:
        if line_payload.procurement_request_id is not None:
            request = procurement_service.get_request(
                db,
                organization_id=organization_id,
                request_id=line_payload.procurement_request_id,
            )
            if request.status != ProcurementRequestStatus.APPROVED:
                raise ConflictError(
                    "Only an APPROVED procurement request can be added to a purchase order",
                    code="request_not_approved",
                )
            linked_requests.append(request)

    lines = [
        PurchaseOrderLine(
            organization_id=organization_id,
            procurement_request_id=line_payload.procurement_request_id,
            part_number=line_payload.part_number,
            description=line_payload.description,
            quantity=line_payload.quantity,
            unit_price_cents=line_payload.unit_price_cents,
        )
        for line_payload in payload.lines
    ]
    subtotal, total = _compute_totals(
        lines, tax_cents=payload.tax_cents, shipping_cents=payload.shipping_cents
    )

    purchase_order = PurchaseOrder(
        organization_id=organization_id,
        po_number=payload.po_number,
        vendor_id=payload.vendor_id,
        aircraft_id=payload.aircraft_id,
        status=PurchaseOrderStatus.DRAFT,
        currency=payload.currency,
        subtotal_cents=subtotal,
        tax_cents=payload.tax_cents,
        shipping_cents=payload.shipping_cents,
        total_cents=total,
        required_by=payload.required_by,
        notes=payload.notes,
        created_by_user_id=actor_user_id,
        lines=lines,
    )
    db.add(purchase_order)
    db.flush()

    for request in linked_requests:
        procurement_service.mark_ordered(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            request_id=request.id,
        )

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="purchase_order.created",
        entity_type="PurchaseOrder",
        entity_id=purchase_order.id,
        metadata={"line_count": len(lines), "total_cents": total},
    )
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


def get_purchase_order(
    db: Session, *, organization_id: uuid.UUID, purchase_order_id: uuid.UUID
) -> PurchaseOrder:
    purchase_order = db.execute(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(
            PurchaseOrder.id == purchase_order_id,
            PurchaseOrder.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if purchase_order is None:
        raise NotFoundError("Purchase order not found")
    return purchase_order


def list_purchase_orders(
    db: Session, *, organization_id: uuid.UUID, status: str | None = None
) -> list[PurchaseOrder]:
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.organization_id == organization_id)
    )
    if status is not None:
        stmt = stmt.where(PurchaseOrder.status == status)
    return list(db.execute(stmt).scalars().all())


def _transition(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    purchase_order: PurchaseOrder,
    target_status: str,
    action: str,
    extra_fields: dict | None = None,
) -> PurchaseOrder:
    _require_transition(purchase_order.status, target_status)
    previous_status = purchase_order.status
    purchase_order.status = target_status
    for field, value in (extra_fields or {}).items():
        setattr(purchase_order, field, value)

    db.add(purchase_order)
    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action=action,
        entity_type="PurchaseOrder",
        entity_id=purchase_order.id,
        metadata={"from_status": previous_status, "to_status": target_status},
    )
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


def submit_for_approval(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, po_id: uuid.UUID
) -> PurchaseOrder:
    purchase_order = get_purchase_order(
        db, organization_id=organization_id, purchase_order_id=po_id
    )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        purchase_order=purchase_order,
        target_status=PurchaseOrderStatus.PENDING_APPROVAL,
        action="purchase_order.submitted_for_approval",
    )


def approve_purchase_order(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, po_id: uuid.UUID
) -> PurchaseOrder:
    purchase_order = get_purchase_order(
        db, organization_id=organization_id, purchase_order_id=po_id
    )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        purchase_order=purchase_order,
        target_status=PurchaseOrderStatus.APPROVED,
        action="purchase_order.approved",
        extra_fields={"approved_by_user_id": actor_user_id},
    )


def send_purchase_order(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, po_id: uuid.UUID
) -> PurchaseOrder:
    purchase_order = get_purchase_order(
        db, organization_id=organization_id, purchase_order_id=po_id
    )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        purchase_order=purchase_order,
        target_status=PurchaseOrderStatus.SENT,
        action="purchase_order.sent",
    )


def acknowledge_purchase_order(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    po_id: uuid.UUID,
    payload: PurchaseOrderAcknowledgeRequest,
) -> PurchaseOrder:
    purchase_order = get_purchase_order(
        db, organization_id=organization_id, purchase_order_id=po_id
    )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        purchase_order=purchase_order,
        target_status=PurchaseOrderStatus.ACKNOWLEDGED,
        action="purchase_order.acknowledged",
        extra_fields={"expected_delivery": payload.expected_delivery},
    )


def cancel_purchase_order(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, po_id: uuid.UUID
) -> PurchaseOrder:
    purchase_order = get_purchase_order(
        db, organization_id=organization_id, purchase_order_id=po_id
    )
    return _transition(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        purchase_order=purchase_order,
        target_status=PurchaseOrderStatus.CANCELLED,
        action="purchase_order.cancelled",
    )
