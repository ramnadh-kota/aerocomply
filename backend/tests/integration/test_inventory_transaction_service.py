import uuid

import pytest
from pydantic import ValidationError

from app.core.errors import ConflictError, NotFoundError
from app.models.part import PartServiceabilityStatus
from app.models.part_requirement import PartRequirementStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.inventory_transaction import (
    InventoryAdjustRequest,
    InventoryConsumeRequest,
    InventoryQuarantineRequest,
    InventoryReceiveRequest,
    InventoryReleaseQuarantineRequest,
    InventoryReleaseRequest,
    InventoryReserveRequest,
)
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    inventory_transaction_service,
    part_requirement_service,
    part_service,
    work_order_service,
)


def _create_part(db_session, org_id, **overrides):
    data = dict(
        part_number="PN-3000",
        description="Brake assembly",
        quantity_on_hand=0,
        quantity_reserved=0,
    )
    data.update(overrides)
    return part_service.create_part(
        db_session, organization_id=org_id, actor_user_id=None, payload=PartCreateRequest(**data)
    )


def _create_work_order(db_session, org_id):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N200AC", msn="MSN-2", aircraft_type="A320"),
    )
    return work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-2000"),
    )


def test_receive_increases_on_hand(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=0)

    inventory_transaction_service.receive_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReceiveRequest(quantity=10),
    )

    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_on_hand == 10
    assert refreshed.available_quantity == 10


def test_reserve_then_release(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5)

    inventory_transaction_service.reserve_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReserveRequest(quantity=3),
    )
    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_reserved == 3
    assert refreshed.available_quantity == 2

    inventory_transaction_service.release_reservation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReleaseRequest(quantity=3),
    )
    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_reserved == 0
    assert refreshed.available_quantity == 5


def test_consume_reduces_on_hand_and_reserved(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5, quantity_reserved=5)

    inventory_transaction_service.consume_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryConsumeRequest(quantity=2),
    )
    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_on_hand == 3
    assert refreshed.quantity_reserved == 3


def test_adjust_negative_writes_off_stock(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5)

    inventory_transaction_service.adjust_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryAdjustRequest(on_hand_delta=-2, notes="Damaged in storage"),
    )
    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_on_hand == 3


def test_consume_cannot_drive_on_hand_negative(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=1, quantity_reserved=1)

    with pytest.raises(ConflictError):
        inventory_transaction_service.consume_part(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            part_id=part.id,
            payload=InventoryConsumeRequest(quantity=5),
        )


def test_reserve_cannot_exceed_on_hand(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=2)

    with pytest.raises(ConflictError):
        inventory_transaction_service.reserve_part(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            part_id=part.id,
            payload=InventoryReserveRequest(quantity=5),
        )


def test_release_cannot_drive_reserved_negative(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5, quantity_reserved=1)

    with pytest.raises(ConflictError):
        inventory_transaction_service.release_reservation(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            part_id=part.id,
            payload=InventoryReleaseRequest(quantity=5),
        )


def test_adjust_zero_delta_rejected():
    with pytest.raises(ValidationError):
        InventoryAdjustRequest(on_hand_delta=0)


def test_receive_on_unknown_part_raises(db_session):
    with pytest.raises(NotFoundError):
        inventory_transaction_service.receive_part(
            db_session,
            organization_id=uuid.uuid4(),
            actor_user_id=None,
            part_id=uuid.uuid4(),
            payload=InventoryReceiveRequest(quantity=1),
        )


def test_receive_cannot_touch_other_tenant_part(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    part = _create_part(db_session, org_a, quantity_on_hand=5)

    with pytest.raises(NotFoundError):
        inventory_transaction_service.receive_part(
            db_session,
            organization_id=org_b,
            actor_user_id=None,
            part_id=part.id,
            payload=InventoryReceiveRequest(quantity=1),
        )


def test_list_transactions_scoped_to_part_and_org(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=0)
    other_part = _create_part(db_session, org_id, part_number="PN-3001", quantity_on_hand=0)

    inventory_transaction_service.receive_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReceiveRequest(quantity=5),
    )
    inventory_transaction_service.receive_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=other_part.id,
        payload=InventoryReceiveRequest(quantity=1),
    )

    transactions = inventory_transaction_service.list_transactions_for_part(
        db_session, organization_id=org_id, part_id=part.id
    )
    assert len(transactions) == 1
    assert transactions[0].on_hand_delta == 5


def test_receiving_stock_flips_short_requirement_to_available(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=0)
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

    inventory_transaction_service.receive_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReceiveRequest(quantity=2),
    )

    refreshed = part_requirement_service.get_part_requirement(
        db_session, organization_id=org_id, requirement_id=requirement.id
    )
    assert refreshed.status == PartRequirementStatus.AVAILABLE


def test_quarantine_removes_from_available_but_not_on_hand(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5)

    inventory_transaction_service.quarantine_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryQuarantineRequest(quantity=2, reason="Suspected corrosion damage"),
    )

    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_on_hand == 5
    assert refreshed.quantity_quarantined == 2
    assert refreshed.available_quantity == 3
    assert refreshed.serviceability_status == PartServiceabilityStatus.QUARANTINED
    assert refreshed.quarantine_reason == "Suspected corrosion damage"


def test_quarantine_cannot_exceed_available_stock(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=2, quantity_reserved=1)

    with pytest.raises(ConflictError):
        inventory_transaction_service.quarantine_part(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            part_id=part.id,
            payload=InventoryQuarantineRequest(quantity=2, reason="Damage check"),
        )


def test_release_quarantine_to_serviceable_restores_availability(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5)
    inventory_transaction_service.quarantine_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryQuarantineRequest(quantity=2, reason="Pending inspection"),
    )

    inventory_transaction_service.release_quarantine(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReleaseQuarantineRequest(
            quantity=2, new_status=PartServiceabilityStatus.SERVICEABLE, notes="Passed inspection"
        ),
    )

    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_on_hand == 5
    assert refreshed.quantity_quarantined == 0
    assert refreshed.available_quantity == 5
    assert refreshed.serviceability_status == PartServiceabilityStatus.SERVICEABLE
    assert refreshed.quarantine_reason is None


def test_release_quarantine_to_scrapped_removes_stock_entirely(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5)
    inventory_transaction_service.quarantine_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryQuarantineRequest(quantity=2, reason="Failed inspection"),
    )

    inventory_transaction_service.release_quarantine(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryReleaseQuarantineRequest(
            quantity=2, new_status=PartServiceabilityStatus.SCRAPPED
        ),
    )

    refreshed = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert refreshed.quantity_on_hand == 3
    assert refreshed.quantity_quarantined == 0
    assert refreshed.serviceability_status == PartServiceabilityStatus.SCRAPPED


def test_release_quarantine_rejects_unknown_status(db_session):
    org_id = uuid.uuid4()
    part = _create_part(db_session, org_id, quantity_on_hand=5)
    inventory_transaction_service.quarantine_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=InventoryQuarantineRequest(quantity=1, reason="Check"),
    )

    with pytest.raises(ConflictError):
        inventory_transaction_service.release_quarantine(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            part_id=part.id,
            payload=InventoryReleaseQuarantineRequest(quantity=1, new_status="MADE_UP_STATUS"),
        )
