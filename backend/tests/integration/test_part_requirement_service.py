import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.part_requirement import PartRequirementStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest, PartRequirementUpdateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    part_requirement_service,
    part_service,
    work_order_service,
)


def _create_part(db_session, org_id, **overrides):
    data = dict(
        part_number="PN-2000",
        description="Hydraulic actuator",
        manufacturer="Acme",
        condition="NEW",
        quantity_on_hand=5,
        quantity_reserved=0,
    )
    data.update(overrides)
    return part_service.create_part(
        db_session, organization_id=org_id, actor_user_id=None, payload=PartCreateRequest(**data)
    )


def _create_work_order(db_session, org_id, **overrides):
    suffix = uuid.uuid4().hex[:6].upper()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(
            registration=f"N{suffix}", msn=f"MSN-{suffix}", aircraft_type="B737-800"
        ),
    )
    data = dict(aircraft_id=aircraft.id, work_order_number=f"WO-{suffix}")
    data.update(overrides)
    return work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(**data),
    )


def test_create_requirement_available_when_stock_sufficient(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5, quantity_reserved=0)
    work_order = _create_work_order(db_session, org_id)

    requirement = part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=2
        ),
    )

    assert requirement.status == PartRequirementStatus.AVAILABLE
    assert requirement.work_order_id == work_order.id


def test_create_requirement_short_when_stock_insufficient(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=1, quantity_reserved=1)
    work_order = _create_work_order(db_session, org_id)

    requirement = part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=2
        ),
    )

    assert requirement.status == PartRequirementStatus.SHORT


def test_create_requirement_unknown_part_raises(db_session):
    org_id = uuid.uuid4()
    work_order = _create_work_order(db_session, org_id)
    with pytest.raises(NotFoundError):
        part_requirement_service.create_part_requirement(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=PartRequirementCreateRequest(
                work_order_id=work_order.id, part_id=uuid.uuid4(), required_quantity=1
            ),
        )


def test_list_requirements_scoped_to_work_order_and_org(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    part_a = _create_part(db_session, org_a)
    work_order_a = _create_work_order(db_session, org_a, work_order_number="WO-A1")
    work_order_a2 = _create_work_order(db_session, org_a, work_order_number="WO-A2")

    part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(work_order_id=work_order_a.id, part_id=part_a.id),
    )
    part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(work_order_id=work_order_a2.id, part_id=part_a.id),
    )

    results = part_requirement_service.list_part_requirements_for_work_order(
        db_session, organization_id=org_a, work_order_id=work_order_a.id
    )
    assert len(results) == 1

    cross_tenant = part_requirement_service.list_part_requirements_for_work_order(
        db_session, organization_id=org_b, work_order_id=work_order_a.id
    )
    assert cross_tenant == []


def test_update_fulfilled_quantity_marks_fulfilled(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5, quantity_reserved=0)
    work_order = _create_work_order(db_session, org_id)
    requirement = part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=2
        ),
    )
    assert requirement.status == PartRequirementStatus.AVAILABLE

    updated = part_requirement_service.update_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=PartRequirementUpdateRequest(fulfilled_quantity=2),
    )
    assert updated.status == PartRequirementStatus.FULFILLED


def test_recompute_status_transitions_short_to_available_after_stock_increase(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=0, quantity_reserved=0)
    work_order = _create_work_order(db_session, org_id)
    requirement = part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=1
        ),
    )
    assert requirement.status == PartRequirementStatus.SHORT

    part.quantity_on_hand = 3
    db_session.add(part)
    db_session.commit()

    refreshed = part_requirement_service.recompute_status_for_part(
        db_session, organization_id=org_id, part_id=part.id
    )
    assert refreshed[0].status == PartRequirementStatus.AVAILABLE


def test_get_requirement_not_found_raises(db_session):
    with pytest.raises(NotFoundError):
        part_requirement_service.get_part_requirement(
            db_session, organization_id=uuid.uuid4(), requirement_id=uuid.uuid4()
        )
