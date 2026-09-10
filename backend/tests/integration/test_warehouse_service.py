import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.schemas.part import PartCreateRequest
from app.schemas.warehouse import LocationCreateRequest, WarehouseCreateRequest
from app.services import part_service, warehouse_service


def _create_warehouse(db_session, org_id, **overrides):
    data = dict(code="STORES-1", name="Main Stores")
    data.update(overrides)
    return warehouse_service.create_warehouse(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=WarehouseCreateRequest(**data),
    )


def test_create_warehouse_and_location(db_session):
    org_id = uuid.uuid4()
    warehouse = _create_warehouse(db_session, org_id)
    location = warehouse_service.create_location(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        warehouse_id=warehouse.id,
        payload=LocationCreateRequest(code="BAY-3", description="Bay 3 shelving"),
    )
    assert location.warehouse_id == warehouse.id
    assert location.code == "BAY-3"


def test_duplicate_warehouse_code_rejected(db_session):
    org_id = uuid.uuid4()
    _create_warehouse(db_session, org_id)

    with pytest.raises(ConflictError):
        _create_warehouse(db_session, org_id)


def test_duplicate_location_code_within_warehouse_rejected(db_session):
    org_id = uuid.uuid4()
    warehouse = _create_warehouse(db_session, org_id)
    warehouse_service.create_location(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        warehouse_id=warehouse.id,
        payload=LocationCreateRequest(code="BAY-1"),
    )

    with pytest.raises(ConflictError):
        warehouse_service.create_location(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            warehouse_id=warehouse.id,
            payload=LocationCreateRequest(code="BAY-1"),
        )


def test_same_location_code_allowed_in_different_warehouses(db_session):
    org_id = uuid.uuid4()
    warehouse_a = _create_warehouse(db_session, org_id, code="WH-A")
    warehouse_b = _create_warehouse(db_session, org_id, code="WH-B")

    loc_a = warehouse_service.create_location(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        warehouse_id=warehouse_a.id,
        payload=LocationCreateRequest(code="BAY-1"),
    )
    loc_b = warehouse_service.create_location(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        warehouse_id=warehouse_b.id,
        payload=LocationCreateRequest(code="BAY-1"),
    )
    assert loc_a.id != loc_b.id


def test_location_scoped_to_tenant(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    warehouse = _create_warehouse(db_session, org_a)
    location = warehouse_service.create_location(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        warehouse_id=warehouse.id,
        payload=LocationCreateRequest(code="BAY-1"),
    )

    with pytest.raises(NotFoundError):
        warehouse_service.get_location(db_session, organization_id=org_b, location_id=location.id)


def test_cannot_create_location_in_other_tenant_warehouse(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    warehouse = _create_warehouse(db_session, org_a)

    with pytest.raises(NotFoundError):
        warehouse_service.create_location(
            db_session,
            organization_id=org_b,
            actor_user_id=None,
            warehouse_id=warehouse.id,
            payload=LocationCreateRequest(code="BAY-1"),
        )


def test_assign_location_to_part_becomes_authoritative(db_session):
    org_id = uuid.uuid4()
    warehouse = _create_warehouse(db_session, org_id)
    location = warehouse_service.create_location(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        warehouse_id=warehouse.id,
        payload=LocationCreateRequest(code="BAY-1"),
    )
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(
            part_number="PN-8000", description="Hydraulic hose", location="Shelf 4 (legacy text)"
        ),
    )
    assert part.location_id is None

    updated = part_service.assign_location(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        part_id=part.id,
        location_id=location.id,
    )
    assert updated.location_id == location.id
    # Legacy free-text field is left untouched — location_id is what callers
    # must now treat as authoritative (see part.py docstring), not erased.
    assert updated.location == "Shelf 4 (legacy text)"


def test_assign_unknown_location_raises(db_session):
    org_id = uuid.uuid4()
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(part_number="PN-8001", description="Bracket"),
    )

    with pytest.raises(NotFoundError):
        part_service.assign_location(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            part_id=part.id,
            location_id=uuid.uuid4(),
        )


def test_list_warehouses_and_locations_scoped_to_tenant(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    _create_warehouse(db_session, org_a)

    assert len(warehouse_service.list_warehouses(db_session, organization_id=org_a)) == 1
    assert warehouse_service.list_warehouses(db_session, organization_id=org_b) == []
