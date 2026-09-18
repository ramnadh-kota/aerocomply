"""M17.6A: receiving a part against a work order's PartRequirement should
increment PartRequirement.fulfilled_quantity and, once fully covered, clear
the MATERIAL release-readiness blocker for that work order.

Before this fix, fulfilled_quantity never moved off 0 anywhere in the
codebase -- release_readiness_service's MATERIAL blocker
(app/services/release_readiness_service.py) reads it directly, so a fully
received part requirement never cleared the blocker. The fix lives in
part_requirement_service.fulfill_from_receipt, called from
receiving_service.receive_purchase_order once it knows which work order/task
the receipt was actually ordered for (via the linked ProcurementRequest).
"""

import uuid

from app.models.part_requirement import PartRequirementStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestCreateRequest,
)
from app.schemas.purchase_order import PurchaseOrderCreateRequest, PurchaseOrderLineCreateRequest
from app.schemas.receiving import ReceiveLineRequest, ReceivePurchaseOrderRequest
from app.schemas.vendor import VendorCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    part_requirement_service,
    part_service,
    procurement_service,
    purchase_order_service,
    receiving_service,
    release_readiness_service,
    vendor_service,
    work_order_service,
)


def _build_work_order_with_requirement(db_session, org_id, *, required_quantity=1):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N900MR", msn="MSN-MR-1", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-MR-1"),
    )
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(
            part_number="PN-MR-1", description="Hydraulic pump", quantity_on_hand=0
        ),
    )
    requirement = part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=required_quantity
        ),
    )
    return {
        "aircraft": aircraft,
        "work_order": work_order,
        "part": part,
        "requirement": requirement,
    }


def _create_sent_po(db_session, org_id, *, work_order_id, part_id, quantity):
    vendor = vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="MR Vendor"),
    )
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N901MR", msn="MSN-MR-2", aircraft_type="A320"),
    )
    request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=aircraft.id,
            work_order_id=work_order_id,
            part_id=part_id,
            part_number="PN-MR-1",
            description="Hydraulic pump",
            quantity=quantity,
            reason="Work order material",
        ),
    )
    approved = procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(selected_vendor_id=vendor.id),
    )
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number=f"PO-MR-{uuid.uuid4().hex[:8]}",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    procurement_request_id=approved.id,
                    part_number="PN-MR-1",
                    description="Hydraulic pump",
                    quantity=quantity,
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
    return po


def test_full_receipt_fulfills_requirement_and_clears_material_blocker(db_session):
    org_id = uuid.uuid4()
    ctx = _build_work_order_with_requirement(db_session, org_id, required_quantity=2)
    po = _create_sent_po(
        db_session, org_id, work_order_id=ctx["work_order"].id, part_id=ctx["part"].id, quantity=2
    )

    readiness_before = release_readiness_service.get_release_readiness_for_work_order(
        db_session, organization_id=org_id, work_order_id=ctx["work_order"].id
    )
    assert any(b.category == "MATERIAL" for b in readiness_before.blockers)

    receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=po.lines[0].id, quantity=2)]
        ),
    )

    refreshed = part_requirement_service.get_part_requirement(
        db_session, organization_id=org_id, requirement_id=ctx["requirement"].id
    )
    assert refreshed.fulfilled_quantity == 2
    assert refreshed.status == PartRequirementStatus.FULFILLED

    readiness_after = release_readiness_service.get_release_readiness_for_work_order(
        db_session, organization_id=org_id, work_order_id=ctx["work_order"].id
    )
    assert not any(b.category == "MATERIAL" for b in readiness_after.blockers)


def test_partial_receipt_keeps_blocker_with_correct_remaining_quantity(db_session):
    org_id = uuid.uuid4()
    ctx = _build_work_order_with_requirement(db_session, org_id, required_quantity=5)
    po = _create_sent_po(
        db_session, org_id, work_order_id=ctx["work_order"].id, part_id=ctx["part"].id, quantity=5
    )

    receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=po.lines[0].id, quantity=3)]
        ),
    )

    refreshed = part_requirement_service.get_part_requirement(
        db_session, organization_id=org_id, requirement_id=ctx["requirement"].id
    )
    assert refreshed.fulfilled_quantity == 3
    assert refreshed.required_quantity - refreshed.fulfilled_quantity == 2
    assert refreshed.status != PartRequirementStatus.FULFILLED

    readiness = release_readiness_service.get_release_readiness_for_work_order(
        db_session, organization_id=org_id, work_order_id=ctx["work_order"].id
    )
    material_blockers = [b for b in readiness.blockers if b.category == "MATERIAL"]
    assert len(material_blockers) == 1
    assert "fulfilled_quantity=3" in material_blockers[0].description
    assert "required_quantity=5" in material_blockers[0].description


def test_concurrent_receiving_against_same_requirement_does_not_lose_updates(db_session):
    """Two receipts landing against the same PartRequirement must both be
    reflected in fulfilled_quantity -- never lost to a naive
    read-modify-write race, and never pushed past required_quantity.

    True multi-connection concurrency can't be modeled under this test
    suite's db_session fixture (tests/integration/conftest.py): each test
    runs inside one already-open connection/transaction that is rolled back
    at teardown, so a row created here is invisible to any second, separate
    connection until a real top-level commit that never happens. What *can*
    be verified directly, without mocking anything, is the property that
    actually prevents lost updates under real concurrency: each call to
    part_requirement_service.fulfill_from_receipt issues a single atomic
    `UPDATE ... SET fulfilled_quantity = LEAST(required_quantity,
    fulfilled_quantity + delta)`, which Postgres evaluates against whatever
    the row's *current* value is at UPDATE time -- so calling it twice in a
    row (standing in for two receipts that would otherwise race to read the
    same stale value) still accumulates both deltas correctly, and can never
    exceed required_quantity even if the deltas summed would.
    """
    org_id = uuid.uuid4()
    ctx = _build_work_order_with_requirement(db_session, org_id, required_quantity=10)

    # Two "concurrent" receipts of 5 each, landing back-to-back before either
    # has re-read the row -- exactly the interleaving a lost update needs.
    part_requirement_service.fulfill_from_receipt(
        db_session,
        organization_id=org_id,
        part_id=ctx["part"].id,
        work_order_id=ctx["work_order"].id,
        task_id=None,
        received_quantity=5,
    )
    part_requirement_service.fulfill_from_receipt(
        db_session,
        organization_id=org_id,
        part_id=ctx["part"].id,
        work_order_id=ctx["work_order"].id,
        task_id=None,
        received_quantity=5,
    )

    refreshed = part_requirement_service.get_part_requirement(
        db_session, organization_id=org_id, requirement_id=ctx["requirement"].id
    )
    assert refreshed.fulfilled_quantity == 10
    assert refreshed.status == PartRequirementStatus.FULFILLED

    # A third, over-eager receipt must not push it past required_quantity.
    part_requirement_service.fulfill_from_receipt(
        db_session,
        organization_id=org_id,
        part_id=ctx["part"].id,
        work_order_id=ctx["work_order"].id,
        task_id=None,
        received_quantity=5,
    )
    refreshed_again = part_requirement_service.get_part_requirement(
        db_session, organization_id=org_id, requirement_id=ctx["requirement"].id
    )
    assert refreshed_again.fulfilled_quantity == 10
