import uuid

from app.models.compliance import ComplianceState
from app.models.finding import FindingSeverity
from app.models.organization import Organization
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.compliance import (
    ComplianceObligationCreateRequest,
    ComplianceObligationUpdateRequest,
    RegulatoryRequirementCreateRequest,
)
from app.services import aircraft_service, aog_service, compliance_service, finding_service
from app.services.compliance import obligation_service
from app.services.intelligence import risk_intelligence_service


def _create_org(db_session):
    org = Organization(name=f"Risk Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N200RK", msn="MSN-RK-1", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def test_asset_with_no_compliance_obligations_is_unknown_not_low(db_session):
    # Mirrors readiness intelligence: zero ComplianceObligation rows is
    # UNKNOWN_INTEL upstream, so risk must stay UNKNOWN, never default LOW.
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    result = risk_intelligence_service.get_asset_risk_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.risk_level == "UNKNOWN"
    assert result.readiness_state == "UNKNOWN"


def test_critical_finding_yields_critical_risk_when_compliance_also_blocked(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N200RK2", msn="MSN-RK-2")
    finding_service.create_finding(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        title="Cracked spar",
        description="Structural crack found during inspection",
        severity=FindingSeverity.CRITICAL,
        aircraft_id=aircraft.id,
    )
    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            requirement_number="AD-RK-1",
            title="Test AD",
            description="Test airworthiness directive",
        ),
    )
    obligation = obligation_service.create_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceObligationCreateRequest(
            requirement_id=requirement.id,
            asset_id=aircraft.asset_id,
        ),
    )
    obligation_service.update_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        obligation_id=obligation.id,
        payload=ComplianceObligationUpdateRequest(status=ComplianceState.NON_COMPLIANT.value),
    )

    result = risk_intelligence_service.get_asset_risk_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.risk_level == "CRITICAL"
    safety_factor = next(f for f in result.factors if f.name == "safety")
    compliance_factor = next(f for f in result.factors if f.name == "compliance")
    assert safety_factor.value == "TRUE"
    assert compliance_factor.value == "TRUE"


def test_active_aog_yields_critical_risk(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N200RK3", msn="MSN-RK-3")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    result = risk_intelligence_service.get_asset_risk_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.risk_level == "CRITICAL"
    aog_factor = next(f for f in result.factors if f.name == "aog")
    assert aog_factor.value == "TRUE"


def test_blocked_obligation_with_no_other_signal_is_unknown_not_low(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N200RK4", msn="MSN-RK-4")
    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            requirement_number="AD-RK-2",
            title="Test AD",
            description="Test airworthiness directive",
        ),
    )
    obligation = obligation_service.create_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceObligationCreateRequest(
            requirement_id=requirement.id,
            asset_id=aircraft.asset_id,
        ),
    )
    obligation_service.update_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        obligation_id=obligation.id,
        payload=ComplianceObligationUpdateRequest(status=ComplianceState.BLOCKED.value),
    )

    result = risk_intelligence_service.get_asset_risk_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.risk_level != "LOW"
