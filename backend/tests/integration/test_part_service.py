import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.part import Part
from app.schemas.part import PartCreateRequest, PartUpdateRequest
from app.services import part_service


def _payload(**overrides) -> PartCreateRequest:
    data = dict(
        part_number="PN-1000",
        description="Fuel pump",
        manufacturer="Acme",
        condition="NEW",
        quantity_on_hand=10,
        quantity_reserved=2,
    )
    data.update(overrides)
    return PartCreateRequest(**data)


def test_create_and_get_part(db_session):
    org_id = uuid.uuid4()
    part = part_service.create_part(
        db_session, organization_id=org_id, actor_user_id=None, payload=_payload()
    )
    assert part.id is not None
    assert part.organization_id == org_id
    assert part.available_quantity == 8

    fetched = part_service.get_part(db_session, organization_id=org_id, part_id=part.id)
    assert fetched.id == part.id


def test_get_part_not_found_raises(db_session):
    with pytest.raises(NotFoundError):
        part_service.get_part(
            db_session, organization_id=uuid.uuid4(), part_id=uuid.uuid4()
        )


def test_list_parts_scoped_to_organization(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    part_service.create_part(
        db_session, organization_id=org_a, actor_user_id=None, payload=_payload()
    )
    part_service.create_part(
        db_session, organization_id=org_b, actor_user_id=None, payload=_payload()
    )

    parts_a = part_service.list_parts(db_session, organization_id=org_a)
    parts_b = part_service.list_parts(db_session, organization_id=org_b)

    assert len(parts_a) == 1
    assert len(parts_b) == 1
    assert parts_a[0].organization_id == org_a


def test_org_b_cannot_get_org_a_part(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    part = part_service.create_part(
        db_session, organization_id=org_a, actor_user_id=None, payload=_payload()
    )

    with pytest.raises(NotFoundError):
        part_service.get_part(db_session, organization_id=org_b, part_id=part.id)


def test_update_part_quantities(db_session):
    org_id = uuid.uuid4()
    part = part_service.create_part(
        db_session, organization_id=org_id, actor_user_id=None, payload=_payload()
    )
    updated = part_service.update_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        payload=PartUpdateRequest(quantity_on_hand=5, quantity_reserved=5),
    )
    assert updated.quantity_on_hand == 5
    assert updated.quantity_reserved == 5
    assert updated.available_quantity == 0


def test_update_part_not_found_raises(db_session):
    with pytest.raises(NotFoundError):
        part_service.update_part(
            db_session,
            organization_id=uuid.uuid4(),
            actor_user_id=None,
            part_id=uuid.uuid4(),
            payload=PartUpdateRequest(quantity_on_hand=1),
        )


def test_shortage_status_true_when_available_zero_or_negative():
    part = Part(quantity_on_hand=5, quantity_reserved=5, quantity_quarantined=0)
    assert part_service.get_shortage_status(part) is True

    part = Part(quantity_on_hand=3, quantity_reserved=5, quantity_quarantined=0)
    assert part_service.get_shortage_status(part) is True


def test_shortage_status_false_when_stock_available():
    part = Part(quantity_on_hand=10, quantity_reserved=2, quantity_quarantined=0)
    assert part_service.get_shortage_status(part) is False
