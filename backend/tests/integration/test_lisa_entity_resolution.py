import uuid

import pytest

from app.core.errors import ConflictError
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.purchase_order import PurchaseOrderCreateRequest, PurchaseOrderLineCreateRequest
from app.schemas.vendor import VendorCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    part_service,
    purchase_order_service,
    vendor_service,
    work_order_service,
)
from app.services.lisa import entity_resolution_service as er
from app.services.lisa.entity_resolution_service import AmbiguousMatch, NotFound, ResolvedEntity


def test_resolve_aircraft_exact_registration(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-XYZ", msn="MSN-1", aircraft_type="A320"),
    )
    result = er.resolve_aircraft(db_session, organization_id=org_id, identifier="vt-xyz")
    assert isinstance(result, ResolvedEntity)
    assert result.entity_id == str(aircraft.id)


def test_resolve_aircraft_by_uuid(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-ABC", msn="MSN-2", aircraft_type="A320"),
    )
    result = er.resolve_aircraft(db_session, organization_id=org_id, identifier=str(aircraft.id))
    assert isinstance(result, ResolvedEntity)
    assert result.display == "VT-ABC"


def test_resolve_aircraft_not_found(db_session):
    org_id = uuid.uuid4()
    result = er.resolve_aircraft(db_session, organization_id=org_id, identifier="ZZ-NOPE")
    assert isinstance(result, NotFound)


def test_duplicate_aircraft_registration_within_org_is_rejected(db_session):
    """resolve_aircraft used to have to handle two aircraft sharing a
    registration within one tenant returning AmbiguousMatch — that data
    state can no longer exist at all: a database-level uniqueness
    constraint (uq_aircraft_organization_id_registration) now rejects the
    second create outright, so this asserts the rejection instead. The
    AmbiguousMatch mechanism itself remains covered by
    test_resolve_work_order_ambiguous below (work orders have no
    equivalent uniqueness constraint).
    """
    org_id = uuid.uuid4()
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-DUP", msn="MSN-3A", aircraft_type="A320"),
    )
    with pytest.raises(ConflictError):
        aircraft_service.create_aircraft(
            db_session,
            organization_id=org_id,
            payload=AircraftCreateRequest(
                registration="VT-DUP", msn="MSN-3B", aircraft_type="B737"
            ),
        )
    # create_aircraft's own db.rollback() (needed to recover the session
    # after the IntegrityError) rolls back this test fixture's single flat
    # transaction, not a savepoint — it takes the earlier "committed" first
    # aircraft with it too. Re-create it to verify resolution still works
    # cleanly after a rejected duplicate, rather than asserting on data
    # this test harness cannot make survive the rollback.
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-DUP", msn="MSN-3A", aircraft_type="A320"),
    )
    result = er.resolve_aircraft(db_session, organization_id=org_id, identifier="VT-DUP")
    assert isinstance(result, ResolvedEntity)


def test_resolve_aircraft_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a,
        payload=AircraftCreateRequest(registration="VT-TEN", msn="MSN-4", aircraft_type="A320"),
    )
    result = er.resolve_aircraft(db_session, organization_id=org_b, identifier="VT-TEN")
    assert isinstance(result, NotFound)


def test_resolve_work_order_exact_number(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N500ER", msn="MSN-5", aircraft_type="A320"),
    )
    wo = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-2001"),
    )
    result = er.resolve_work_order(db_session, organization_id=org_id, identifier="wo-2001")
    assert isinstance(result, ResolvedEntity)
    assert result.entity_id == str(wo.id)


def test_resolve_work_order_ambiguous(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N501ER", msn="MSN-6", aircraft_type="A320"),
    )
    work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-DUP"),
    )
    work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-DUP"),
    )
    result = er.resolve_work_order(db_session, organization_id=org_id, identifier="WO-DUP")
    assert isinstance(result, AmbiguousMatch)


def test_resolve_part_exact_number(db_session):
    org_id = uuid.uuid4()
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(part_number="PN-9000", description="Widget"),
    )
    result = er.resolve_part(db_session, organization_id=org_id, identifier="pn-9000")
    assert isinstance(result, ResolvedEntity)
    assert result.entity_id == str(part.id)


def test_resolve_vendor_exact_name(db_session):
    org_id = uuid.uuid4()
    vendor = vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="Skyline Aero Parts"),
    )
    result = er.resolve_vendor(db_session, organization_id=org_id, identifier="skyline aero parts")
    assert isinstance(result, ResolvedEntity)
    assert result.entity_id == str(vendor.id)


def test_resolve_purchase_order_exact_number(db_session):
    org_id = uuid.uuid4()
    vendor = vendor_service.create_vendor(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=VendorCreateRequest(name="V1"),
    )
    po = purchase_order_service.create_purchase_order(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PurchaseOrderCreateRequest(
            po_number="PO-7000",
            vendor_id=vendor.id,
            lines=[PurchaseOrderLineCreateRequest(part_number="PN-1", description="x", quantity=1)],
        ),
    )
    result = er.resolve_purchase_order(db_session, organization_id=org_id, identifier="po-7000")
    assert isinstance(result, ResolvedEntity)
    assert result.entity_id == str(po.id)
