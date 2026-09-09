import uuid

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models.aog_event import AogEventStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogBlockerCreateRequest, AogEventCreateRequest
from app.services import aircraft_service, aog_service


def _create_aircraft(db_session, org_id):
    return aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N600AC", msn="MSN-7", aircraft_type="B737"),
    )


def _declare(db_session, org_id, **overrides):
    aircraft = _create_aircraft(db_session, org_id)
    data = dict(aircraft_id=aircraft.id)
    data.update(overrides)
    return aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(**data),
    )


def test_declare_aog_starts_declared(db_session):
    org_id = uuid.uuid4()
    event = _declare(db_session, org_id, severity="CRITICAL")
    assert event.status == AogEventStatus.DECLARED
    assert event.severity == "CRITICAL"
    assert event.blockers == []


def test_cannot_mark_recovered_with_unresolved_blockers(db_session):
    org_id = uuid.uuid4()
    event = _declare(db_session, org_id)
    aog_service.start_recovery(
        db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
    )
    aog_service.add_blocker(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        event_id=event.id,
        payload=AogBlockerCreateRequest(
            blocker_type="MATERIAL", description="Hydraulic pump on backorder"
        ),
    )

    with pytest.raises(ConflictError):
        aog_service.mark_recovered(
            db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
        )


def test_resolving_all_blockers_allows_recovery(db_session):
    org_id = uuid.uuid4()
    event = _declare(db_session, org_id)
    aog_service.start_recovery(
        db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
    )
    event = aog_service.add_blocker(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        event_id=event.id,
        payload=AogBlockerCreateRequest(
            blocker_type="MATERIAL", description="Hydraulic pump on backorder"
        ),
    )
    blocker_id = event.blockers[0].id

    event = aog_service.resolve_blocker(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        event_id=event.id,
        blocker_id=blocker_id,
    )
    assert event.blockers[0].resolved is True

    recovered = aog_service.mark_recovered(
        db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
    )
    assert recovered.status == AogEventStatus.RECOVERED


def test_cannot_skip_declared_to_recovered(db_session):
    org_id = uuid.uuid4()
    event = _declare(db_session, org_id)
    with pytest.raises(ConflictError):
        aog_service.mark_recovered(
            db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
        )


def test_cancel_from_declared(db_session):
    org_id = uuid.uuid4()
    event = _declare(db_session, org_id)
    cancelled = aog_service.cancel_aog_event(
        db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
    )
    assert cancelled.status == AogEventStatus.CANCELLED


def test_list_events_filters_by_aircraft_and_status(db_session):
    org_id = uuid.uuid4()
    event_a = _declare(db_session, org_id)
    _declare(db_session, org_id)

    by_aircraft = aog_service.list_aog_events(
        db_session, organization_id=org_id, aircraft_id=event_a.aircraft_id
    )
    assert len(by_aircraft) == 1
    assert by_aircraft[0].id == event_a.id

    by_status = aog_service.list_aog_events(
        db_session, organization_id=org_id, status=AogEventStatus.DECLARED
    )
    assert len(by_status) == 2


def test_get_event_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    event = _declare(db_session, org_a)

    with pytest.raises(NotFoundError):
        aog_service.get_aog_event(db_session, organization_id=org_b, event_id=event.id)


def test_resolve_unknown_blocker_raises(db_session):
    org_id = uuid.uuid4()
    event = _declare(db_session, org_id)

    with pytest.raises(NotFoundError):
        aog_service.resolve_blocker(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            event_id=event.id,
            blocker_id=uuid.uuid4(),
        )
