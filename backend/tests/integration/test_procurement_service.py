import uuid

import pytest

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.models.organization import Organization
from app.models.procurement_request import ProcurementRequestStatus
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.procurement_request import (
    ProcurementRequestApproveRequest,
    ProcurementRequestCreateRequest,
    ProcurementRequestRejectRequest,
)
from app.services import aircraft_service, procurement_service


def _create_user(db_session, org_id, **overrides):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()

    data = dict(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test User",
    )
    data.update(overrides)
    user = User(**data)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_aircraft(db_session, org_id):
    return aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N300AC", msn="MSN-3", aircraft_type="B777"),
    )


def _create_request(db_session, org_id, requester_id=None, **overrides):
    aircraft = _create_aircraft(db_session, org_id)
    data = dict(
        aircraft_id=aircraft.id,
        part_number="PN-5000",
        description="Wheel bearing",
        quantity=2,
        reason="Required for WO-3000 gear inspection finding.",
    )
    data.update(overrides)
    return procurement_service.create_request(
        db_session,
        organization_id=org_id,
        actor_user_id=requester_id,
        payload=ProcurementRequestCreateRequest(**data),
    )


def test_create_request_starts_submitted(db_session):
    org_id = uuid.uuid4()
    request = _create_request(db_session, org_id)
    assert request.status == ProcurementRequestStatus.SUBMITTED


def test_full_lifecycle_submitted_to_closed(db_session):
    org_id = uuid.uuid4()
    requester_id = _create_user(db_session, org_id).id
    approver_id = _create_user(db_session, org_id).id
    request = _create_request(db_session, org_id, requester_id=requester_id)

    approved = procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=approver_id,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(),
    )
    assert approved.status == ProcurementRequestStatus.APPROVED
    assert approved.approved_by_user_id == approver_id

    ordered = procurement_service.mark_ordered(
        db_session, organization_id=org_id, actor_user_id=approver_id, request_id=request.id
    )
    assert ordered.status == ProcurementRequestStatus.ORDERED

    received = procurement_service.mark_received(
        db_session, organization_id=org_id, actor_user_id=approver_id, request_id=request.id
    )
    assert received.status == ProcurementRequestStatus.RECEIVED

    closed = procurement_service.close_request(
        db_session, organization_id=org_id, actor_user_id=approver_id, request_id=request.id
    )
    assert closed.status == ProcurementRequestStatus.CLOSED


def test_requester_cannot_approve_own_request(db_session):
    org_id = uuid.uuid4()
    requester_id = _create_user(db_session, org_id).id
    request = _create_request(db_session, org_id, requester_id=requester_id)

    with pytest.raises(ForbiddenError):
        procurement_service.approve_request(
            db_session,
            organization_id=org_id,
            actor_user_id=requester_id,
            request_id=request.id,
            payload=ProcurementRequestApproveRequest(),
        )


def test_reject_records_reason(db_session):
    org_id = uuid.uuid4()
    request = _create_request(db_session, org_id)

    rejected = procurement_service.reject_request(
        db_session,
        organization_id=org_id,
        actor_user_id=uuid.uuid4(),
        request_id=request.id,
        payload=ProcurementRequestRejectRequest(rejection_reason="Duplicate of PR-1"),
    )
    assert rejected.status == ProcurementRequestStatus.REJECTED
    assert rejected.rejection_reason == "Duplicate of PR-1"


def test_cannot_skip_approved_to_received(db_session):
    org_id = uuid.uuid4()
    approver_id = _create_user(db_session, org_id).id
    request = _create_request(db_session, org_id)
    procurement_service.approve_request(
        db_session,
        organization_id=org_id,
        actor_user_id=approver_id,
        request_id=request.id,
        payload=ProcurementRequestApproveRequest(),
    )

    with pytest.raises(ConflictError):
        procurement_service.mark_received(
            db_session, organization_id=org_id, actor_user_id=None, request_id=request.id
        )


def test_cannot_approve_already_rejected_request(db_session):
    org_id = uuid.uuid4()
    approver_id = _create_user(db_session, org_id).id
    request = _create_request(db_session, org_id)
    procurement_service.reject_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        request_id=request.id,
        payload=ProcurementRequestRejectRequest(rejection_reason="Not needed"),
    )

    with pytest.raises(ConflictError):
        procurement_service.approve_request(
            db_session,
            organization_id=org_id,
            actor_user_id=approver_id,
            request_id=request.id,
            payload=ProcurementRequestApproveRequest(),
        )


def test_get_request_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    request = _create_request(db_session, org_a)

    with pytest.raises(NotFoundError):
        procurement_service.get_request(db_session, organization_id=org_b, request_id=request.id)


def test_list_requests_filters_by_status(db_session):
    org_id = uuid.uuid4()
    request_a = _create_request(db_session, org_id)
    _create_request(db_session, org_id)
    procurement_service.reject_request(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        request_id=request_a.id,
        payload=ProcurementRequestRejectRequest(rejection_reason="No longer needed"),
    )

    rejected_only = procurement_service.list_requests(
        db_session, organization_id=org_id, status=ProcurementRequestStatus.REJECTED
    )
    assert len(rejected_only) == 1
    assert rejected_only[0].id == request_a.id
