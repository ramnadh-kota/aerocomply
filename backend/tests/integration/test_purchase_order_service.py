import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models.organization import Organization
from app.models.procurement_request import ProcurementRequestStatus
from app.models.purchase_order import PurchaseOrderStatus
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestCreateRequest,
)
from app.schemas.purchase_order import (
    PurchaseOrderAcknowledgeRequest,
    PurchaseOrderCreateRequest,
    PurchaseOrderLineCreateRequest,
)
from app.schemas.vendor import VendorCreateRequest
from app.services import (
    aircraft_service,
    procurement_service,
    purchase_order_service,
    vendor_service,
)


def _create_user(db_session, org_id):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_vendor(db_session, org_id):
    return vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="Acme Aerospace"),
    )


def _create_approved_request(db_session, org_id, approver_id):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N400AC", msn="MSN-4", aircraft_type="A320"),
    )
    request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=aircraft.id,
            part_number="PN-6000",
            description="Hydraulic pump",
            quantity=1,
            reason="AOG recovery",
        ),
    )
    return procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=approver_id,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(),
    )


def test_create_purchase_order_computes_totals(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)

    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-1000",
            vendor_id=vendor.id,
            tax_cents=500,
            shipping_cents=1000,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-6000",
                    description="Hydraulic pump",
                    quantity=2,
                    unit_price_cents=10000,
                ),
                PurchaseOrderLineCreateRequest(
                    part_number="PN-6001", description="Seal kit", quantity=1
                ),
            ],
        ),
    )

    assert po.status == PurchaseOrderStatus.DRAFT
    assert po.subtotal_cents == 20000
    assert po.total_cents == 21500
    assert len(po.lines) == 2


def test_create_purchase_order_links_and_advances_approved_request(db_session):
    org_id = uuid.uuid4()
    approver = _create_user(db_session, org_id)
    vendor = _create_vendor(db_session, org_id)
    approved_request = _create_approved_request(db_session, org_id, approver.id)

    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=approver.id,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-1001",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    procurement_request_id=approved_request.id,
                    part_number="PN-6000",
                    description="Hydraulic pump",
                    quantity=1,
                    unit_price_cents=15000,
                )
            ],
        ),
    )

    assert po.lines[0].procurement_request_id == approved_request.id

    refreshed_request = procurement_service.get_request(
        db_session, organization_id=org_id, request_id=approved_request.id
    )
    assert refreshed_request.status == ProcurementRequestStatus.ORDERED


def test_create_purchase_order_rejects_unapproved_request(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N401AC", msn="MSN-5", aircraft_type="A320"),
    )
    unapproved_request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=aircraft.id,
            part_number="PN-6002",
            description="Filter",
            reason="Routine replacement",
        ),
    )

    with pytest.raises(ConflictError):
        purchase_order_service.create_purchase_order(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=PurchaseOrderCreateRequest(
                po_number="PO-1002",
                vendor_id=vendor.id,
                lines=[
                    PurchaseOrderLineCreateRequest(
                        procurement_request_id=unapproved_request.id,
                        part_number="PN-6002",
                        description="Filter",
                        quantity=1,
                    )
                ],
            ),
        )


def test_full_lifecycle_draft_to_acknowledged(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-1003",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-6003", description="Gasket", quantity=1
                )
            ],
        ),
    )

    po = purchase_order_service.submit_for_approval(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    assert po.status == PurchaseOrderStatus.PENDING_APPROVAL

    po = purchase_order_service.approve_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    assert po.status == PurchaseOrderStatus.APPROVED

    po = purchase_order_service.send_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    assert po.status == PurchaseOrderStatus.SENT

    po = purchase_order_service.acknowledge_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=PurchaseOrderAcknowledgeRequest(),
    )
    assert po.status == PurchaseOrderStatus.ACKNOWLEDGED


def test_cannot_skip_draft_to_approved(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-1004",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-6004", description="Bolt kit", quantity=1
                )
            ],
        ),
    )

    with pytest.raises(ConflictError):
        purchase_order_service.approve_purchase_order(
            db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
        )


def test_cancel_from_draft(db_session):
    org_id = uuid.uuid4()
    vendor = _create_vendor(db_session, org_id)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-1005",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-6005", description="Clamp", quantity=1
                )
            ],
        ),
    )
    cancelled = purchase_order_service.cancel_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    assert cancelled.status == PurchaseOrderStatus.CANCELLED


def test_get_purchase_order_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    vendor = _create_vendor(db_session, org_a)
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-1006",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    part_number="PN-6006", description="O-ring", quantity=1
                )
            ],
        ),
    )

    with pytest.raises(NotFoundError):
        purchase_order_service.get_purchase_order(
            db_session, organization_id=org_b, purchase_order_id=po.id
        )
