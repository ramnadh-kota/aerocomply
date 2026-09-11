import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import NotFoundError
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.technician import TechnicianQualificationCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, technician_service, work_order_service


def _create_user(db_session, org_id):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test Technician",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _setup_task(db_session, org_id, aircraft_type="A320"):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(
            registration="N900TQ", msn="MSN-TQ", aircraft_type=aircraft_type
        ),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-TQ-1"),
    )
    task = work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Replace fuel pump"),
    )
    return aircraft, work_order, task


def test_check_authorization_missing_when_no_qualification(db_session):
    org_id = uuid.uuid4()
    technician = _create_user(db_session, org_id)
    _, _, task = _setup_task(db_session, org_id)

    result = technician_service.check_authorization(
        db_session, organization_id=org_id, task_id=task.id, technician_user_id=technician.id
    )
    assert result.status == "MISSING"


def test_check_authorization_authorized_with_valid_qualification(db_session):
    org_id = uuid.uuid4()
    technician = _create_user(db_session, org_id)
    _, _, task = _setup_task(db_session, org_id, aircraft_type="A320")

    technician_service.grant_qualification(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=technician.id, aircraft_type="A320", qualification_type="AIRFRAME_POWERPLANT"
        ),
    )

    result = technician_service.check_authorization(
        db_session, organization_id=org_id, task_id=task.id, technician_user_id=technician.id
    )
    assert result.status == "AUTHORIZED"
    assert result.qualification_id is not None


def test_check_authorization_expired(db_session):
    org_id = uuid.uuid4()
    technician = _create_user(db_session, org_id)
    _, _, task = _setup_task(db_session, org_id, aircraft_type="A320")

    technician_service.grant_qualification(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=technician.id,
            aircraft_type="A320",
            qualification_type="AIRFRAME_POWERPLANT",
            granted_at=datetime.now(UTC) - timedelta(days=400),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )

    result = technician_service.check_authorization(
        db_session, organization_id=org_id, task_id=task.id, technician_user_id=technician.id
    )
    assert result.status == "EXPIRED"


def test_check_authorization_not_authorized_when_revoked(db_session):
    org_id = uuid.uuid4()
    technician = _create_user(db_session, org_id)
    _, _, task = _setup_task(db_session, org_id, aircraft_type="A320")

    qualification = technician_service.grant_qualification(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=technician.id, aircraft_type="A320", qualification_type="AIRFRAME_POWERPLANT"
        ),
    )
    technician_service.revoke_qualification(
        db_session, organization_id=org_id, actor_user_id=None, qualification_id=qualification.id
    )

    result = technician_service.check_authorization(
        db_session, organization_id=org_id, task_id=task.id, technician_user_id=technician.id
    )
    assert result.status == "NOT_AUTHORIZED"


def test_check_authorization_wrong_aircraft_type_is_missing(db_session):
    org_id = uuid.uuid4()
    technician = _create_user(db_session, org_id)
    _, _, task = _setup_task(db_session, org_id, aircraft_type="A320")

    technician_service.grant_qualification(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=technician.id, aircraft_type="B737", qualification_type="AIRFRAME_POWERPLANT"
        ),
    )

    result = technician_service.check_authorization(
        db_session, organization_id=org_id, task_id=task.id, technician_user_id=technician.id
    )
    assert result.status == "MISSING"


def test_check_authorization_unknown_technician(db_session):
    org_id = uuid.uuid4()
    _, _, task = _setup_task(db_session, org_id)

    result = technician_service.check_authorization(
        db_session, organization_id=org_id, task_id=task.id, technician_user_id=uuid.uuid4()
    )
    assert result.status == "UNKNOWN"


def test_assign_technician_sets_task_field(db_session):
    org_id = uuid.uuid4()
    technician = _create_user(db_session, org_id)
    _, _, task = _setup_task(db_session, org_id)

    updated = technician_service.assign_technician(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        task_id=task.id,
        technician_user_id=technician.id,
    )
    assert updated.assigned_technician_user_id == technician.id


def test_qualification_and_authorization_are_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    technician_a = _create_user(db_session, org_a)
    _, _, task_a = _setup_task(db_session, org_a, aircraft_type="A320")

    technician_service.grant_qualification(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=TechnicianQualificationCreateRequest(
            user_id=technician_a.id, aircraft_type="A320", qualification_type="AIRFRAME_POWERPLANT"
        ),
    )

    # org_b cannot see org_a's task at all.
    with pytest.raises(NotFoundError):
        technician_service.check_authorization(
            db_session, organization_id=org_b, task_id=task_a.id, technician_user_id=technician_a.id
        )

    # org_b cannot assign a technician to org_a's task.
    with pytest.raises(NotFoundError):
        technician_service.assign_technician(
            db_session,
            organization_id=org_b,
            actor_user_id=None,
            task_id=task_a.id,
            technician_user_id=technician_a.id,
        )
