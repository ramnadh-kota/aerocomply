import uuid

import pytest

from app.core.errors import NotFoundError
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
from app.services.intelligence import priority_intelligence_service


def _create_org(db_session):
    org = Organization(name=f"Priority Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N300PR", msn="MSN-PR-1", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def _create_requirement_and_obligation(db_session, org_id, aircraft, status, req_number):
    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            requirement_number=req_number,
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
        payload=ComplianceObligationUpdateRequest(status=status),
    )
    return obligation


def test_unknown_intel_never_becomes_low_priority(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    result = priority_intelligence_service.get_asset_priority_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.priority_level == "UNKNOWN"
    assert result.risk_level == "UNKNOWN"
    assert result.readiness_state == "UNKNOWN"


def test_nominal_asset_is_low_priority(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N300PR2", msn="MSN-PR-2")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-PR-1"
    )

    result = priority_intelligence_service.get_asset_priority_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.priority_level == "LOW"
    assert result.readiness_state == "READY"
    assert result.blocker_count == 0
    assert result.escalated is False


def test_degraded_state_from_open_minor_finding_is_low_priority_with_warning(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N300PR3", msn="MSN-PR-3")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-PR-2"
    )
    finding_service.create_finding(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        title="Minor paint scuff",
        description="Cosmetic finding, no airworthiness impact",
        severity=FindingSeverity.MINOR,
        aircraft_id=aircraft.id,
    )

    result = priority_intelligence_service.get_asset_priority_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.readiness_state == "READY"
    assert result.warning_count >= 1
    assert result.priority_level == "LOW"


def test_restricted_state_from_non_compliant_obligation_is_high_priority(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N300PR4", msn="MSN-PR-4")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-PR-3"
    )

    result = priority_intelligence_service.get_asset_priority_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.readiness_state == "BLOCKED"
    assert result.priority_level == "HIGH"


def test_grounded_intel_from_active_aog_is_critical_priority(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N300PR5", msn="MSN-PR-5")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    result = priority_intelligence_service.get_asset_priority_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.priority_level == "CRITICAL"
    assert result.readiness_state == "BLOCKED"


def test_three_or_more_blockers_escalate_priority_one_tier(db_session):
    # Three unresolved MAJOR findings each read identically to one under
    # risk_intelligence_service's binary safety factor (which only counts
    # CRITICAL severity) -- but compliance is still driven TRUE by the
    # overall aerospace state being RESTRICTED, so risk_level is HIGH here.
    # With 3 concrete blockers present, priority's escalation rule fires:
    # HIGH -> CRITICAL.
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N300PR6", msn="MSN-PR-6")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-PR-4"
    )
    for i in range(3):
        finding_service.create_finding(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            title=f"Major finding {i}",
            description="Major finding requiring corrective action",
            severity=FindingSeverity.MAJOR,
            aircraft_id=aircraft.id,
        )

    result = priority_intelligence_service.get_asset_priority_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.blocker_count >= 3
    assert result.risk_level == "HIGH"
    assert result.priority_level == "CRITICAL"
    assert result.escalated is True


def test_priority_intelligence_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_a, registration="N300PR7", msn="MSN-PR-7")

    with pytest.raises(NotFoundError):
        priority_intelligence_service.get_asset_priority_intelligence(
            db_session, organization_id=org_b, asset_id=aircraft.asset_id
        )
