import uuid

import pytest

from app.core.errors import AeroComplyError, NotFoundError
from app.models.assessment import AssessmentScopeType, AssessmentStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.assessment import AssessmentCreateRequest
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
    aog_service,
    part_requirement_service,
    part_service,
    procurement_service,
    purchase_order_service,
    receiving_service,
    vendor_service,
    work_order_service,
)
from app.services.assessment import engine


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
    _create_user(db_session, org_id)
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N701AC", msn="MSN-501", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-ASSESS-1"),
    )
    aog_service.declare_aog(
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
            part_number="PN-ASSESS-1", description="Hydraulic pump", quantity_on_hand=0
        ),
    )
    part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=1
        ),
    )
    return {"org_id": org_id, "aircraft": aircraft, "work_order": work_order, "part": part}


def test_create_assessment_fleet_scope(db_session):
    org_id = uuid.uuid4()
    _create_user(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    assert assessment.scope_type == AssessmentScopeType.FLEET
    assert assessment.status == AssessmentStatus.DRAFT


def test_create_assessment_aircraft_scope_requires_scope_id(db_session):
    org_id = uuid.uuid4()
    _create_user(db_session, org_id)
    with pytest.raises(AeroComplyError):
        engine.create_assessment(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=AssessmentCreateRequest(name="Bad", scope_type=AssessmentScopeType.AIRCRAFT),
        )


def test_run_assessment_with_no_data_produces_healthy_empty_snapshot(db_session):
    org_id = uuid.uuid4()
    _create_user(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Empty Fleet"),
    )
    snapshot = engine.run_assessment(
        db_session, organization_id=org_id, actor_user_id=None, assessment_id=assessment.id
    )
    assert snapshot.version == 1
    assert snapshot.finding_count == 0
    assert snapshot.overall_score == 100.0
    assert snapshot.maturity_band == "HEALTHY"


def test_run_assessment_surfaces_aog_material_shortage_finding(db_session):
    org_id = uuid.uuid4()
    _setup_aog_with_shortage(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    snapshot = engine.run_assessment(
        db_session, organization_id=org_id, actor_user_id=None, assessment_id=assessment.id
    )
    assert snapshot.finding_count >= 1
    categories = [f.category for f in snapshot.findings]
    assert "MATERIAL_NOT_REQUESTED" in categories

    finding = next(f for f in snapshot.findings if f.category == "MATERIAL_NOT_REQUESTED")
    assert finding.entity_type == "Aircraft" or finding.entity_type is not None
    # Every risk carries an honest UNKNOWN likelihood — never a fabricated probability.
    risk = next(r for r in snapshot.risks if r.finding_id == finding.id)
    assert risk.likelihood == "UNKNOWN"
    # Roadmap sequencing follows priority rank (highest materiality first).
    assert snapshot.roadmap_items[0].sequence == 1


def test_run_assessment_resolves_finding_as_supply_chain_progresses(db_session):
    org_id = uuid.uuid4()
    ctx = _setup_aog_with_shortage(db_session, org_id)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Fleet Assessment"),
    )
    first_snapshot = engine.run_assessment(
        db_session, organization_id=org_id, actor_user_id=None, assessment_id=assessment.id
    )
    assert any(f.category == "MATERIAL_NOT_REQUESTED" for f in first_snapshot.findings)

    vendor = vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="V"),
    )
    request = procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ProcurementRequestCreateRequest(
            aircraft_id=ctx["aircraft"].id,
            work_order_id=ctx["work_order"].id,
            part_id=ctx["part"].id,
            part_number="PN-ASSESS-1",
            description="Hydraulic pump",
            quantity=1,
            reason="AOG shortage",
        ),
    )
    approver = _create_user(db_session, org_id)
    procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=approver.id,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(),
    )
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            vendor_id=vendor.id,
            po_number="PO-ASSESS-1",
            lines=[
                PurchaseOrderLineCreateRequest(
                    procurement_request_id=request.id,
                    part_id=ctx["part"].id,
                    part_number="PN-ASSESS-1",
                    description="Hydraulic pump",
                    quantity=1,
                    unit_price=10,
                )
            ],
        ),
    )
    purchase_order_service.submit_for_approval(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    purchase_order_service.approve_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    purchase_order_service.send_purchase_order(
        db_session, organization_id=org_id, actor_user_id=None, po_id=po.id
    )
    receiving_service.receive_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        po_id=po.id,
        payload=ReceivePurchaseOrderRequest(
            lines=[ReceiveLineRequest(line_id=po.lines[0].id, quantity=1)]
        ),
    )

    second_snapshot = engine.run_assessment(
        db_session, organization_id=org_id, actor_user_id=None, assessment_id=assessment.id
    )
    assert second_snapshot.version == 2
    categories = [f.category for f in second_snapshot.findings]
    assert "MATERIAL_NOT_REQUESTED" not in categories
    assert "MATERIAL_AWAITING_RECEIPT" not in categories

    comparison = engine.compare_snapshots(
        db_session,
        organization_id=org_id,
        snapshot_id_a=first_snapshot.id,
        snapshot_id_b=second_snapshot.id,
    )
    assert comparison.from_version == 1
    assert comparison.to_version == 2
    assert any("MATERIAL_NOT_REQUESTED" in r for r in comparison.resolved_findings)


def test_tenant_isolation_on_assessment(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    _create_user(db_session, org_a)
    _create_user(db_session, org_b)
    assessment = engine.create_assessment(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=AssessmentCreateRequest(name="Org A Assessment"),
    )
    with pytest.raises(NotFoundError):
        engine.get_assessment(db_session, organization_id=org_b, assessment_id=assessment.id)
    assert engine.list_assessments(db_session, organization_id=org_b) == []
