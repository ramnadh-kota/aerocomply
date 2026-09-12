import uuid

import pytest

from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, work_order_service
from app.services.lisa import context_service
from app.services.lisa.message_resolution_service import resolve_message


def _create_user(db_session, org_id):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Lisa Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_get_or_create_context_creates_once(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    first = context_service.get_or_create_context(
        db_session, organization_id=org_id, user_id=user_id
    )
    second = context_service.get_or_create_context(
        db_session, organization_id=org_id, user_id=user_id
    )
    assert first.id == second.id


def test_update_context_sets_field_and_bumps_version(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    context = context_service.get_or_create_context(
        db_session, organization_id=org_id, user_id=user_id
    )
    aircraft_id = str(uuid.uuid4())
    updated = context_service.update_context(
        db_session, context, updates={"current_aircraft_id": aircraft_id}
    )
    assert str(updated.current_aircraft_id) == aircraft_id
    assert updated.context_version == 2


def test_update_context_rejects_unknown_field(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    context = context_service.get_or_create_context(
        db_session, organization_id=org_id, user_id=user_id
    )
    with pytest.raises(ValueError):
        context_service.update_context(db_session, context, updates={"not_a_real_field": "x"})


def test_reset_context_clears_entities_but_not_history(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    context = context_service.get_or_create_context(
        db_session, organization_id=org_id, user_id=user_id
    )
    context_service.update_context(
        db_session, context, updates={"current_aircraft_id": str(uuid.uuid4())}
    )
    context_service.record_question(db_session, context, question="Why is it AOG?")
    reset = context_service.reset_context(db_session, context)
    assert reset.current_aircraft_id is None
    assert reset.previous_question is None
    assert reset.recent_questions == "[]"


def test_record_question_tracks_previous_and_recent(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    context = context_service.get_or_create_context(
        db_session, organization_id=org_id, user_id=user_id
    )
    context_service.record_question(db_session, context, question="Q1")
    context = context_service.record_question(db_session, context, question="Q2")
    assert context.previous_question == "Q2"


def test_message_resolution_explicit_aircraft_updates_context(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-MSG", msn="MSN-MSG", aircraft_type="A320"),
    )
    resolution = resolve_message(
        db_session, organization_id=org_id, user_id=user_id, question="Why is VT-MSG still AOG?"
    )
    assert not resolution.needs_clarification
    assert str(resolution.context.current_aircraft_id) == str(aircraft.id)


def test_message_resolution_pronoun_follows_prior_explicit_resolution(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-FLW", msn="MSN-FLW", aircraft_type="A320"),
    )
    resolve_message(db_session, organization_id=org_id, user_id=user_id, question="Open VT-FLW.")
    follow_up = resolve_message(
        db_session, organization_id=org_id, user_id=user_id, question="What is blocking release?"
    )
    # No explicit identifier in the follow-up and no matching pronoun phrase
    # either — context.current_aircraft_id must still carry over untouched.
    assert str(follow_up.context.current_aircraft_id) == str(aircraft.id)


def test_message_resolution_this_aircraft_pronoun_resolves_from_context(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-PRN", msn="MSN-PRN", aircraft_type="A320"),
    )
    resolve_message(db_session, organization_id=org_id, user_id=user_id, question="Open VT-PRN.")
    follow_up = resolve_message(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        question="What is blocking this aircraft?",
    )
    assert len(follow_up.resolved) == 1
    assert follow_up.resolved[0].entity_id == str(aircraft.id)


def test_message_resolution_switches_aircraft_on_new_explicit_reference(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    first = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-OLD", msn="MSN-OLD", aircraft_type="A320"),
    )
    second = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-NEW", msn="MSN-NEW", aircraft_type="B737"),
    )
    resolve_message(db_session, organization_id=org_id, user_id=user_id, question="Open VT-OLD.")
    switched = resolve_message(
        db_session, organization_id=org_id, user_id=user_id, question="Switch to VT-NEW."
    )
    assert str(switched.context.current_aircraft_id) == str(second.id)
    assert str(switched.context.current_aircraft_id) != str(first.id)


def test_message_resolution_ambiguous_short_circuits(db_session):
    """Aircraft can no longer produce this ambiguity (a database-level
    uniqueness constraint on (organization_id, registration) now rejects a
    duplicate registration outright — see uq_aircraft_organization_id_registration),
    so this uses work orders instead, which have no equivalent constraint
    and are already proven ambiguity-capable by
    test_resolve_work_order_ambiguous.
    """
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-AMB", msn="MSN-A1", aircraft_type="A320"),
    )
    for _ in range(2):
        work_order_service.create_work_order(
            db_session,
            organization_id=org_id,
            created_by_user_id=None,
            payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-AMB"),
        )
    resolution = resolve_message(
        db_session, organization_id=org_id, user_id=user_id, question="Why is WO-AMB blocked?"
    )
    assert resolution.needs_clarification
    assert resolution.ambiguous is not None
    assert len(resolution.ambiguous.candidates) == 2


def test_message_resolution_reset_phrase_clears_context(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-RST", msn="MSN-RST", aircraft_type="A320"),
    )
    resolve_message(db_session, organization_id=org_id, user_id=user_id, question="Open VT-RST.")
    reset = resolve_message(
        db_session, organization_id=org_id, user_id=user_id, question="Let's start over."
    )
    assert reset.context_reset
    assert reset.context.current_aircraft_id is None


def test_message_resolution_resolves_bare_uuid_from_ambiguity_candidate(db_session):
    """Regression test for a real defect found during the 5b9c2bf QA pass:
    Lisa surfaces a real UUID as a disambiguation option (e.g. "WO-DUP —
    Work Order <uuid>") but had no way to resolve that same UUID if the
    user replied with it — extract_explicit_identifiers only matched
    WO-/PO-/registration-shaped tokens, never a bare UUID. A user could
    never actually select the record Lisa just offered them.

    Uses work orders (not aircraft) to construct the ambiguity: a
    database-level uniqueness constraint on aircraft registration
    (uq_aircraft_organization_id_registration) now makes duplicate aircraft
    registrations impossible, but work orders have no equivalent
    constraint, so they still reproduce the ambiguous-candidate scenario
    this regression guards.
    """
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-UID", msn="MSN-U1", aircraft_type="A320"),
    )
    first = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-UID"),
    )
    work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-UID"),
    )

    ambiguous = resolve_message(
        db_session, organization_id=org_id, user_id=user_id, question="Why is WO-UID blocked?"
    )
    assert ambiguous.needs_clarification

    # The user replies with the exact UUID Lisa surfaced, embedded in a
    # normal sentence — this must resolve to that specific work order.
    resolution = resolve_message(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        question=f"I mean work order {first.id}.",
    )
    assert not resolution.needs_clarification
    assert resolution.resolved
    assert resolution.resolved[0].entity_id == str(first.id)
    assert str(resolution.context.current_work_order_id) == str(first.id)


def test_message_resolution_bare_uuid_from_other_tenant_does_not_resolve(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_b = _create_user(db_session, org_b).id
    aircraft_a = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a,
        payload=AircraftCreateRequest(registration="VT-TUX", msn="MSN-TUX", aircraft_type="A320"),
    )

    resolution = resolve_message(
        db_session,
        organization_id=org_b,
        user_id=user_b,
        question=f"Tell me about {aircraft_a.id}.",
    )
    assert not resolution.needs_clarification
    assert not resolution.resolved
    assert resolution.context.current_aircraft_id is None


def test_message_resolution_context_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = _create_user(db_session, org_a).id
    user_b = _create_user(db_session, org_b).id
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a,
        payload=AircraftCreateRequest(registration="VT-ISO", msn="MSN-ISO", aircraft_type="A320"),
    )
    resolve_message(db_session, organization_id=org_a, user_id=user_a, question="Open VT-ISO.")
    other_tenant = resolve_message(
        db_session, organization_id=org_b, user_id=user_b, question="Why is VT-ISO AOG?"
    )
    # org_b has no aircraft named VT-ISO — must be NOT_FOUND, never resolved
    # against org_a's real record.
    assert not other_tenant.resolved
    assert len(other_tenant.not_found) == 1


def test_message_resolution_work_order_context_persists_across_turns(db_session):
    org_id = uuid.uuid4()
    user_id = _create_user(db_session, org_id).id
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="VT-WOF", msn="MSN-WOF", aircraft_type="A320"),
    )
    wo = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-5050"),
    )
    resolve_message(db_session, organization_id=org_id, user_id=user_id, question="Open WO-5050.")
    follow_up = resolve_message(
        db_session,
        organization_id=org_id,
        user_id=user_id,
        question="Who is assigned to that work order?",
    )
    assert follow_up.resolved[0].entity_id == str(wo.id)
