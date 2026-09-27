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
from app.services.intelligence import decision_service


def _create_org(db_session):
    org = Organization(name=f"Decision Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N400DE", msn="MSN-DE-1", aircraft_type="B737")
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


def test_unknown_intel_yields_insufficient_data_decision(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    result = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.decision_state == "INSUFFICIENT_DATA"
    assert result.required_information
    # UNKNOWN must never be silently resolved into a positive/nominal decision.
    assert result.decision_state not in (
        "NO_ACTION_REQUIRED",
        "MONITOR",
        "ACTION_REQUIRED",
        "IMMEDIATE_ACTION_REQUIRED",
    )


def test_nominal_asset_yields_no_action_required(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N400DE2", msn="MSN-DE-2")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-DE-1"
    )

    result = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.decision_state == "NO_ACTION_REQUIRED"
    assert result.blockers == []


def test_degraded_state_yields_monitor(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N400DE3", msn="MSN-DE-3")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-DE-2"
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

    result = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.decision_state == "MONITOR"
    assert result.warnings


def test_restricted_state_yields_action_required(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N400DE4", msn="MSN-DE-4")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-DE-3"
    )

    result = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.decision_state == "ACTION_REQUIRED"
    assert result.blockers


def test_grounded_intel_yields_immediate_action_required(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N400DE5", msn="MSN-DE-5")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    result = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.decision_state == "IMMEDIATE_ACTION_REQUIRED"
    assert result.priority_level == "CRITICAL"


def test_decision_is_deterministic_across_repeated_calls(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N400DE6", msn="MSN-DE-6")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-DE-4"
    )

    first = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )
    second = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert first.decision_state == second.decision_state
    assert first.decision_reason == second.decision_reason
    assert len(first.blockers) == len(second.blockers)


def test_decision_traceability_preserves_source_record_ids(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N400DE7", msn="MSN-DE-7")
    obligation = _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-DE-5"
    )

    result = decision_service.get_asset_decision(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    aerospace_state_blocker = next(
        b for b in result.blockers if b.source_domain == "AEROSPACE_STATE"
    )
    assert aerospace_state_blocker.related_record_id == obligation.id
    assert aerospace_state_blocker.related_record_type == "ComplianceObligation"


def test_decision_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_a, registration="N400DE8", msn="MSN-DE-8")

    with pytest.raises(NotFoundError):
        decision_service.get_asset_decision(
            db_session, organization_id=org_b, asset_id=aircraft.asset_id
        )


def test_decision_invalid_asset_raises_not_found(db_session):
    org_id = uuid.uuid4()

    with pytest.raises(NotFoundError):
        decision_service.get_asset_decision(
            db_session, organization_id=org_id, asset_id=uuid.uuid4()
        )
