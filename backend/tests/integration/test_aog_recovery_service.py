import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestCreateRequest,
)
from app.schemas.purchase_order import PurchaseOrderCreateRequest, PurchaseOrderLineCreateRequest
from app.schemas.receiving import ReceiveLineRequest, ReceivePurchaseOrderRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.technician import TechnicianQualificationCreateRequest
from app.schemas.vendor import VendorCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    aog_recovery_service,
    aog_service,
    part_requirement_service,
    part_service,
    procurement_service,
    purchase_order_service,
    receiving_service,
    technician_service,
    vendor_service,
    work_order_service,
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


def _setup_aog_with_shortage(db_session, org_id):
    """Aircraft -> AOG event -> work order -> part requirement (SHORT)."""
    approver = _create_user(db_session, org_id)
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N700AC", msn="MSN-9", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-AOG-1"),
    )
    event = aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(
            aircraft_id=aircraft.id, work_order_id=work_order.id, severity="CRITICAL"
        ),
    )
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(
            part_number="PN-AOG-1", description="Fuel pump", quantity_on_hand=0
        ),
    )
    requirement = part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=1
        ),
    )
    return {
        "org_id": org_id,
        "approver": approver,
        "aircraft": aircraft,
        "work_order": work_order,
        "event": event,
        "part": part,
        "requirement": requirement,
    }


def test_no_active_event_reports_not_aog(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N800AC", msn="MSN-10", aircraft_type="A320"),
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert status.is_aog is False
    assert status.blockers == []
    assert status.next_best_action is None


def test_unknown_aircraft_raises_not_found(db_session):
    org_id = uuid.uuid4()
    with pytest.raises(NotFoundError):
        aog_recovery_service.get_recovery_status(
            db_session, organization_id=org_id, aircraft_id=uuid.uuid4()
        )


def test_shortage_not_requested_yields_material_not_requested_blocker(db_session):
    ctx = _setup_aog_with_shortage(db_session, uuid.uuid4())
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=ctx["org_id"], aircraft_id=ctx["aircraft"].id
    )
    assert status.is_aog is True
    assert status.aog_status == "DECLARED"
    categories = [b.category for b in status.blockers]
    assert "MATERIAL_NOT_REQUESTED" in categories
    assert status.next_best_action is not None
    assert status.next_best_action.category == "MATERIAL_NOT_REQUESTED"
    # Honesty guarantees — never fabricated.
    assert status.tat_status == "UNKNOWN"
    assert "UNKNOWN" in status.technician_authorization
    assert "UNKNOWN" in status.eta
    assert "NOT_EVALUATED" in status.compliance_status


def test_full_supply_chain_progression_updates_blocker_category(db_session):
    org_id = uuid.uuid4()
    ctx = _setup_aog_with_shortage(db_session, org_id)
    vendor = vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="AOG Vendor"),
    )

    request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=ctx["aircraft"].id,
            work_order_id=ctx["work_order"].id,
            part_id=ctx["part"].id,
            part_number="PN-AOG-1",
            description="Fuel pump",
            quantity=1,
            reason="AOG recovery",
        ),
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    assert status.next_best_action.category == "MATERIAL_AWAITING_APPROVAL"

    approved = procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=ctx["approver"].id,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(selected_vendor_id=vendor.id),
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    assert status.next_best_action.category == "MATERIAL_PO_NOT_SENT"

    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=ctx["approver"].id,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-AOG-1",
            vendor_id=vendor.id,
            lines=[
                PurchaseOrderLineCreateRequest(
                    procurement_request_id=approved.id,
                    part_number="PN-AOG-1",
                    description="Fuel pump",
                    quantity=1,
                )
            ],
        ),
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    assert status.next_best_action.category == "MATERIAL_PO_NOT_SENT"

    purchase_order_service.submit_for_approval(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    purchase_order_service.approve_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    purchase_order_service.send_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    assert status.next_best_action.category == "MATERIAL_AWAITING_RECEIPT"

    line_id = po.lines[0].id
    receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=line_id, quantity=1)]
        ),
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    # Requirement is now AVAILABLE (no longer SHORT), so no MATERIAL_* blocker
    # remains at all — the shortage genuinely resolved.
    categories = [b.category for b in status.blockers]
    assert not any(c.startswith("MATERIAL") for c in categories)


def test_recovery_status_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    ctx = _setup_aog_with_shortage(db_session, org_a)
    with pytest.raises(NotFoundError):
        aog_recovery_service.get_recovery_status(
            db_session, organization_id=org_b, aircraft_id=ctx["aircraft"].id
        )


def test_critical_path_reflects_material_stage_for_shortage(db_session):
    ctx = _setup_aog_with_shortage(db_session, uuid.uuid4())
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=ctx["org_id"], aircraft_id=ctx["aircraft"].id
    )
    by_stage = {s.stage: s for s in status.critical_path}
    assert by_stage["PART"].status == "BLOCKED"
    assert by_stage["PROCUREMENT"].status == "WAITING"
    assert by_stage["PURCHASE_ORDER"].status == "WAITING"
    assert by_stage["RECEIVING"].status == "WAITING"


def test_critical_path_no_technician_stage_without_task(db_session):
    ctx = _setup_aog_with_shortage(db_session, uuid.uuid4())
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=ctx["org_id"], aircraft_id=ctx["aircraft"].id
    )
    stage_names = [s.stage for s in status.critical_path]
    # No Task rows were created in this fixture, so TECHNICIAN is genuinely
    # not applicable — never fabricated as COMPLETE or BLOCKED.
    assert "TECHNICIAN" not in stage_names


def test_technician_stage_unknown_when_task_exists_but_unassigned(db_session):
    org_id = uuid.uuid4()
    ctx = _setup_aog_with_shortage(db_session, org_id)
    work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=ctx["work_order"].id, description="Install part"),
    )
    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    by_stage = {s.stage: s for s in status.critical_path}
    assert by_stage["TECHNICIAN"].status == "UNKNOWN"
    assert "assigned technician" in status.technician_authorization


def test_technician_stage_blocked_then_complete_after_qualification(db_session):
    org_id = uuid.uuid4()
    ctx = _setup_aog_with_shortage(db_session, org_id)
    technician = _create_user(db_session, org_id)
    task = work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=ctx["work_order"].id, description="Install part"),
    )
    technician_service.assign_technician(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        task_id=task.id,
        technician_user_id=technician.id,
    )

    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    by_stage = {s.stage: s for s in status.critical_path}
    assert by_stage["TECHNICIAN"].status == "BLOCKED"
    assert "MISSING" in by_stage["TECHNICIAN"].reason

    technician_service.grant_qualification(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=technician.id, aircraft_type="A320", qualification_type="AIRFRAME_POWERPLANT"
        ),
    )

    status = aog_recovery_service.get_recovery_status(
        db_session, organization_id=org_id, aircraft_id=ctx["aircraft"].id
    )
    by_stage = {s.stage: s for s in status.critical_path}
    assert by_stage["TECHNICIAN"].status == "COMPLETE"
    assert "AUTHORIZED" in status.technician_authorization
