import datetime
import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.compliance import ComplianceAssessmentStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.compliance import (
    ComplianceAssessmentCreateRequest,
    ComplianceAssessmentOverrideRequest,
    RegulatoryRequirementCreateRequest,
)
from app.services import aircraft_service, compliance_service


def _create_user(db_session, org_id):
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
        db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N900AC", msn="MSN-11", aircraft_type="A320")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def _create_requirement(db_session, org_id, **overrides):
    data = dict(
        authority="FAA",
        requirement_number="AD-2026-01-01",
        title="Wing spar inspection",
        description="Repetitive inspection of wing spar per AD.",
    )
    data.update(overrides)
    return compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(**data),
    )


def test_create_assessment_defaults_unknown(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = _create_requirement(db_session, org_id)

    assessment = compliance_service.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft.id,
            requirement_id=requirement.id,
            evaluated_at=datetime.date.today(),
        ),
    )
    assert assessment.status == ComplianceAssessmentStatus.UNKNOWN
    assert assessment.override_reason is None


def test_create_assessment_unknown_requirement_raises(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    with pytest.raises(NotFoundError):
        compliance_service.create_assessment(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=ComplianceAssessmentCreateRequest(
                aircraft_id=aircraft.id,
                requirement_id=uuid.uuid4(),
                evaluated_at=datetime.date.today(),
            ),
        )


def test_override_records_reason_and_actor(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = _create_requirement(db_session, org_id)
    assessment = compliance_service.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft.id,
            requirement_id=requirement.id,
            status=ComplianceAssessmentStatus.NON_COMPLIANT,
            evaluated_at=datetime.date.today(),
        ),
    )
    actor_id = _create_user(db_session, org_id).id

    overridden = compliance_service.override_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=actor_id,
        assessment_id=assessment.id,
        payload=ComplianceAssessmentOverrideRequest(
            status=ComplianceAssessmentStatus.COMPLIANT,
            override_reason="Manual review confirmed compliance via alternate means of compliance.",
        ),
    )
    assert overridden.status == ComplianceAssessmentStatus.COMPLIANT
    assert overridden.overridden_by_user_id == actor_id
    assert "alternate means" in overridden.override_reason


def test_compliance_analytics_counts_by_status(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement_a = _create_requirement(db_session, org_id, requirement_number="AD-2026-01-01")
    requirement_b = _create_requirement(db_session, org_id, requirement_number="AD-2026-01-02")

    compliance_service.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft.id,
            requirement_id=requirement_a.id,
            status=ComplianceAssessmentStatus.COMPLIANT,
            evaluated_at=datetime.date.today(),
        ),
    )
    compliance_service.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft.id,
            requirement_id=requirement_b.id,
            status=ComplianceAssessmentStatus.NON_COMPLIANT,
            evaluated_at=datetime.date.today(),
        ),
    )

    analytics = compliance_service.get_compliance_analytics(
        db_session, organization_id=org_id, aircraft_id=aircraft.id
    )
    assert analytics == {"COMPLIANT": 1, "NON_COMPLIANT": 1}


def test_list_assessments_scoped_to_aircraft(db_session):
    org_id = uuid.uuid4()
    aircraft_a = _create_aircraft(db_session, org_id, registration="N901AC")
    aircraft_b = _create_aircraft(db_session, org_id, registration="N902AC", msn="MSN-12")
    requirement = _create_requirement(db_session, org_id)

    compliance_service.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft_a.id,
            requirement_id=requirement.id,
            evaluated_at=datetime.date.today(),
        ),
    )

    results_a = compliance_service.list_assessments_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft_a.id
    )
    results_b = compliance_service.list_assessments_for_aircraft(
        db_session, organization_id=org_id, aircraft_id=aircraft_b.id
    )
    assert len(results_a) == 1
    assert results_b == []


def test_get_requirement_cross_tenant_raises(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    requirement = _create_requirement(db_session, org_a)

    with pytest.raises(NotFoundError):
        compliance_service.get_requirement(
            db_session, organization_id=org_b, requirement_id=requirement.id
        )
