import datetime
import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models.deferred_item import DeferredItemApprovalStatus, DeferredItemStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.deferred_item import (
    DeferredItemCloseRequest,
    DeferredItemCreateRequest,
    DeferredItemUpdateRequest,
)
from app.services import aircraft_service, deferred_item_service


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N800AC", msn="MSN-10", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def _create_item(db_session, org_id, **overrides):
    aircraft = _create_aircraft(db_session, org_id)
    data = dict(
        aircraft_id=aircraft.id,
        description="APU generator inoperative",
        opened_at=datetime.date.today(),
    )
    data.update(overrides)
    return deferred_item_service.create_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=DeferredItemCreateRequest(**data),
    )


def test_create_without_approval_required_starts_not_required(db_session):
    org_id = uuid.uuid4()
    item = _create_item(db_session, org_id)
    assert item.status == DeferredItemStatus.OPEN
    assert item.approval_status == DeferredItemApprovalStatus.NOT_REQUIRED


def test_create_with_approval_required_starts_pending(db_session):
    org_id = uuid.uuid4()
    item = _create_item(db_session, org_id, approval_required=True)
    assert item.approval_status == DeferredItemApprovalStatus.PENDING


def test_cannot_close_pending_approval_item(db_session):
    org_id = uuid.uuid4()
    item = _create_item(db_session, org_id, approval_required=True)

    with pytest.raises(ConflictError):
        deferred_item_service.close_deferred_item(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            item_id=item.id,
            payload=DeferredItemCloseRequest(closed_at=datetime.date.today()),
        )


def test_can_close_after_approval(db_session):
    org_id = uuid.uuid4()
    item = _create_item(db_session, org_id, approval_required=True)
    deferred_item_service.update_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        item_id=item.id,
        payload=DeferredItemUpdateRequest(approval_status=DeferredItemApprovalStatus.APPROVED),
    )

    closed = deferred_item_service.close_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        item_id=item.id,
        payload=DeferredItemCloseRequest(closed_at=datetime.date.today(), closure_notes="Fixed"),
    )
    assert closed.status == DeferredItemStatus.CLOSED
    assert closed.closure_notes == "Fixed"


def test_cannot_close_already_closed_item(db_session):
    org_id = uuid.uuid4()
    item = _create_item(db_session, org_id)
    deferred_item_service.close_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        item_id=item.id,
        payload=DeferredItemCloseRequest(closed_at=datetime.date.today()),
    )

    with pytest.raises(ConflictError):
        deferred_item_service.close_deferred_item(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            item_id=item.id,
            payload=DeferredItemCloseRequest(closed_at=datetime.date.today()),
        )


def test_list_for_aircraft_open_only_filter(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    open_item = deferred_item_service.create_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=DeferredItemCreateRequest(
            aircraft_id=aircraft.id, description="Item A", opened_at=datetime.date.today()
        ),
    )
    closed_item = deferred_item_service.create_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=DeferredItemCreateRequest(
            aircraft_id=aircraft.id, description="Item B", opened_at=datetime.date.today()
        ),
    )
    deferred_item_service.close_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        item_id=closed_item.id,
        payload=DeferredItemCloseRequest(closed_at=datetime.date.today()),
    )

    all_items = deferred_item_service.list_deferred_items_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    open_items = deferred_item_service.list_deferred_items_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id, open_only=True
    )
    assert len(all_items) == 2
    assert len(open_items) == 1
    assert open_items[0].id == open_item.id


def test_get_item_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    item = _create_item(db_session, org_a)

    with pytest.raises(NotFoundError):
        deferred_item_service.get_deferred_item(db_session, organization_id=org_b, item_id=item.id)


def test_due_at_defaults_to_unknown(db_session):
    org_id = uuid.uuid4()
    item = _create_item(db_session, org_id)
    assert item.due_at is None
