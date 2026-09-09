import datetime
import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.maintenance_requirement import MaintenanceIntervalType
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.maintenance_requirement import (
    MaintenanceAccomplishmentCreateRequest,
    MaintenanceApplicabilityCreateRequest,
    MaintenanceRequirementCreateRequest,
)
from app.services import aircraft_service, maintenance_service


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N700AC", msn="MSN-8", aircraft_type="A320")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def _create_calendar_requirement(db_session, org_id, interval_days=90):
    return maintenance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=MaintenanceRequirementCreateRequest(
            description="A-check inspection",
            ata_chapter="05",
            interval_type=MaintenanceIntervalType.CALENDAR,
            calendar_interval_days=interval_days,
        ),
    )


def test_no_accomplishment_yields_unknown(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = _create_calendar_requirement(db_session, org_id)
    maintenance_service.add_applicability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
    )

    due = maintenance_service.get_maintenance_due_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert len(due) == 1
    assert due[0].due_status == "UNKNOWN"
    assert due[0].due_date is None


def test_flight_hour_interval_always_unknown(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = maintenance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=MaintenanceRequirementCreateRequest(
            description="Engine borescope",
            ata_chapter="72",
            interval_type=MaintenanceIntervalType.FLIGHT_HOURS,
            fh_interval=500,
        ),
    )
    maintenance_service.add_applicability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
    )
    maintenance_service.record_accomplishment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceAccomplishmentCreateRequest(
            aircraft_id=aircraft.id, accomplished_at=datetime.date.today()
        ),
    )

    due = maintenance_service.get_maintenance_due_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert due[0].due_status == "UNKNOWN"
    assert "utilization" in due[0].reason


def test_overdue_calendar_requirement(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = _create_calendar_requirement(db_session, org_id, interval_days=30)
    maintenance_service.add_applicability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
    )
    maintenance_service.record_accomplishment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceAccomplishmentCreateRequest(
            aircraft_id=aircraft.id,
            accomplished_at=datetime.date.today() - datetime.timedelta(days=60),
        ),
    )

    due = maintenance_service.get_maintenance_due_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert due[0].due_status == "OVERDUE"


def test_not_due_calendar_requirement(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = _create_calendar_requirement(db_session, org_id, interval_days=365)
    maintenance_service.add_applicability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
    )
    maintenance_service.record_accomplishment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceAccomplishmentCreateRequest(
            aircraft_id=aircraft.id, accomplished_at=datetime.date.today()
        ),
    )

    due = maintenance_service.get_maintenance_due_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert due[0].due_status == "NOT_DUE"


def test_latest_accomplishment_used_when_multiple_exist(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = _create_calendar_requirement(db_session, org_id, interval_days=100)
    maintenance_service.add_applicability(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
    )
    maintenance_service.record_accomplishment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceAccomplishmentCreateRequest(
            aircraft_id=aircraft.id,
            accomplished_at=datetime.date.today() - datetime.timedelta(days=200),
        ),
    )
    maintenance_service.record_accomplishment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        requirement_id=requirement.id,
        payload=MaintenanceAccomplishmentCreateRequest(
            aircraft_id=aircraft.id, accomplished_at=datetime.date.today()
        ),
    )

    due = maintenance_service.get_maintenance_due_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert due[0].last_accomplished_at == datetime.date.today()
    assert due[0].due_status == "NOT_DUE"


def test_requirement_not_applicable_produces_no_due_item(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    _create_calendar_requirement(db_session, org_id)

    due = maintenance_service.get_maintenance_due_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert due == []


def test_fleet_due_covers_multiple_aircraft(db_session):
    org_id = uuid.uuid4()
    aircraft_a = _create_aircraft(db_session, org_id, registration="N701AC")
    aircraft_b = _create_aircraft(db_session, org_id, registration="N702AC", msn="MSN-9")
    requirement = _create_calendar_requirement(db_session, org_id)
    for aircraft in (aircraft_a, aircraft_b):
        maintenance_service.add_applicability(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            requirement_id=requirement.id,
            payload=MaintenanceApplicabilityCreateRequest(aircraft_id=aircraft.id),
        )

    fleet_due = maintenance_service.get_fleet_maintenance_due(db_session, organization_id=org_id)
    assert len(fleet_due) == 2


def test_get_requirement_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    requirement = _create_calendar_requirement(db_session, org_a)

    with pytest.raises(NotFoundError):
        maintenance_service.get_requirement(
            db_session, organization_id=org_b, requirement_id=requirement.id
        )
