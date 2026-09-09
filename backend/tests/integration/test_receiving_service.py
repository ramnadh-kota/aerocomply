import uuid

import pytest

from app.core.errors import ConflictError
from app.models.procurement_request import ProcurementRequestStatus
from app.models.purchase_order import PurchaseOrderStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestCreateRequest,
)
from app.schemas.purchase_order import PurchaseOrderCreateRequest, PurchaseOrderLineCreateRequest
from app.schemas.receiving import ReceiveLineRequest, ReceivePurchaseOrderRequest
from app.schemas.vendor import VendorCreateRequest
from app.services import (
    aircraft_service,
    part_service,
    procurement_service,
    purchase_order_service,
    receiving_service,
    vendor_service,
)


def _create_vendor(db_session, org_id):
    return vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="Acme"),
    )


def _create_sent_po_for_part(db_session, org_id, quantity=5):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N500AC", msn="MSN-6", aircraft_type="A320"),
    )
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(
            part_number="PN-7000", description="Fuel valve", quantity_on_hand=0
        ),
    )
    request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=aircraft.id,
            part_id=part.id,
            part_number="PN-7000",
            description="Fuel valve",
            quantity=quantity,
            reason="Stock replenishment",
        ),
    )
    approved = procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(),
    )
    vendor = _create_vendor(db_session, org_id)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-2000",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    procurement_request_id=approved.id,
                    part_number="PN-7000",
                    description="Fuel valve",
                    quantity=quantity,
                    unit_price_cents=5000,
                )
            ],
        ),
    )
    po = purchase_order_service.submit_for_approval(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    po = purchase_order_service.approve_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    po = purchase_order_service.send_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    return po, part


def test_full_receipt_marks_po_received_and_updates_inventory(db_session):
    org_id = uuid.uuid4()
    po, part = _create_sent_po_for_part(db_session, org_id, quantity=5)
    line_id = po.lines[0].id

    received_po = receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=line_id, quantity=5)]
        ),
    )

    assert received_po.status == PurchaseOrderStatus.RECEIVED
    assert received_po.lines[0].received_quantity == 5

    refreshed_part = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed_part.quantity_on_hand == 5


def test_partial_receipt_marks_po_partially_received(db_session):
    org_id = uuid.uuid4()
    po, part = _create_sent_po_for_part(db_session, org_id, quantity=5)
    line_id = po.lines[0].id

    received_po = receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=line_id, quantity=2)]
        ),
    )
    assert received_po.status == PurchaseOrderStatus.PARTIALLY_RECEIVED
    assert received_po.lines[0].received_quantity == 2

    refreshed_part = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed_part.quantity_on_hand == 2

    fully_received_po = receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=line_id, quantity=3)]
        ),
    )
    assert fully_received_po.status == PurchaseOrderStatus.RECEIVED


def test_over_receipt_rejected(db_session):
    org_id = uuid.uuid4()
    po, _ = _create_sent_po_for_part(db_session, org_id, quantity=5)
    line_id = po.lines[0].id

    with pytest.raises(ConflictError):
        receiving_service.receive_purchase_order(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            po_id=po.id,
            payload=ReceivePurchaseOrderRequest(
                lines=[ReceiveLineRequest(line_id=line_id, quantity=6)]
            ),
        )


def test_cannot_receive_against_draft_po(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-2001",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-7001", description="Bolt", quantity=1
                )
            ],
        ),
    )

    with pytest.raises(ConflictError):
        receiving_service.receive_purchase_order(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            po_id=po.id,
            payload=ReceivePurchaseOrderRequest(
                lines=[ReceiveLineRequest(line_id=po.lines[0].id, quantity=1)]
            ),
        )


def test_full_receipt_advances_procurement_request_to_received(db_session):
    org_id = uuid.uuid4()
    po, _ = _create_sent_po_for_part(db_session, org_id, quantity=1)
    line_id = po.lines[0].id
    request_id = po.lines[0].procurement_request_id

    receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=line_id, quantity=1)]
        ),
    )

    refreshed_request = procurement_service.get_request(
        db_session, organization_id=org_id, request_id=request_id
    )
    assert refreshed_request.status == ProcurementRequestStatus.RECEIVED


def test_receipt_with_unlinked_line_does_not_touch_inventory(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-2002",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-7002", description="Generic hardware", quantity=3
                )
            ],
        ),
    )
    po = purchase_order_service.submit_for_approval(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    po = purchase_order_service.approve_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    po = purchase_order_service.send_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )

    received_po = receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=po.lines[0].id, quantity=3)]
        ),
    )
    assert received_po.status == PurchaseOrderStatus.RECEIVED
