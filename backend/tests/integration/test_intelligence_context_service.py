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
from app.services.intelligence import context_service


def _create_org(db_session):
    org = Organization(name=f"Context Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N700CX", msn="MSN-CX-1", aircraft_type="B737")
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
            authority="FAA", requirement_number=req_number, title="Test AD", description="Test AD"
        ),
    )
    obligation = obligation_service.create_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceObligationCreateRequest(
            requirement_id=requirement.id, asset_id=aircraft.asset_id
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


def test_contract_version_and_required_fields_present(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id)
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-CX-1"
    )

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert ctx.contract_version == "1.0"
    assert ctx.tenant.organization_id == org_id
    assert ctx.asset.asset_id == aircraft.asset_id
    assert ctx.generated_at is not None


def test_context_composes_all_five_sections_plus_aerospace_state(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N700CX2", msn="MSN-CX-2")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-CX-2"
    )

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert ctx.readiness.state == "READY"
    assert ctx.risk.level == "LOW"
    assert ctx.priority.level == "LOW"
    assert ctx.decision.state == "NO_ACTION_REQUIRED"
    assert ctx.recommendation.state == "NO_ACTION_REQUIRED"
    assert ctx.aerospace_state.status == "NOMINAL"
    assert ctx.uncertainty == []


def test_unknown_intel_never_becomes_nominal_in_context(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert ctx.aerospace_state.status == "UNKNOWN_INTEL"
    assert ctx.aerospace_state.status != "NOMINAL"
    assert ctx.readiness.state == "UNKNOWN"
    assert ctx.risk.level == "UNKNOWN"
    assert ctx.decision.state == "INSUFFICIENT_DATA"
    assert ctx.decision.state != "NO_ACTION_REQUIRED"
    assert ctx.recommendation.state == "INSUFFICIENT_DATA"
    assert len(ctx.uncertainty) > 0


def test_grounded_intel_and_critical_priority_surface_through_context(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N700CX3", msn="MSN-CX-3")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert ctx.aerospace_state.status == "GROUNDED_INTEL"
    assert ctx.priority.level == "CRITICAL"
    assert ctx.decision.state == "IMMEDIATE_ACTION_REQUIRED"


def test_blocker_and_source_traceability_survive_context_construction(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N700CX4", msn="MSN-CX-4")
    obligation = _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-CX-4"
    )

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    # Full D2.1 detail (blocker_id, what_condition) survives in aerospace_state,
    # which D2.2's own flattened readiness.blockers do not carry.
    aerospace_blocker = next(
        b for b in ctx.aerospace_state.blockers if str(obligation.id) in str(b.source_ref.source_id)
    )
    assert aerospace_blocker.blocker_id
    assert aerospace_blocker.what_condition
    assert aerospace_blocker.source_ref.source_id == obligation.id
    assert aerospace_blocker.source_ref.source_type == "ComplianceObligation"

    readiness_blocker = next(
        b for b in ctx.readiness.blockers if b.related_record_id == obligation.id
    )
    assert readiness_blocker.required_action
    assert readiness_blocker.related_record_type == "ComplianceObligation"

    recommendation_item = next(
        item
        for item in ctx.recommendation.items
        if item.source_blocker and item.source_blocker.related_record_id == obligation.id
    )
    assert recommendation_item.action_category == "PERFORM_REQUIRED_ACTION"


def test_open_finding_warning_survives_context_construction(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N700CX5", msn="MSN-CX-5")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-CX-5"
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

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert ctx.aerospace_state.status == "DEGRADED"
    assert len(ctx.aerospace_state.warnings) >= 1
    assert ctx.decision.state == "MONITOR"


def test_context_is_tenant_scoped(db_session):
    org_a = _create_org(db_session)
    org_b = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_a, registration="N700CX6", msn="MSN-CX-6")

    with pytest.raises(NotFoundError):
        context_service.get_asset_intelligence_context(
            db_session, organization_id=org_b, asset_id=aircraft.asset_id
        )


def test_context_invalid_asset_raises_not_found(db_session):
    org_id = uuid.uuid4()

    with pytest.raises(NotFoundError):
        context_service.get_asset_intelligence_context(
            db_session, organization_id=org_id, asset_id=uuid.uuid4()
        )


def test_context_is_deterministic_across_repeated_calls(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N700CX7", msn="MSN-CX-7")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-CX-7"
    )

    first = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )
    second = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert first.decision.state == second.decision.state
    assert first.readiness.state == second.readiness.state
    assert first.risk.level == second.risk.level
    assert len(first.readiness.blockers) == len(second.readiness.blockers)


def test_context_serializes_to_json_and_back(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N700CX8", msn="MSN-CX-8")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-CX-8"
    )

    ctx = context_service.get_asset_intelligence_context(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    from app.schemas.intelligence import IntelligenceContext

    payload = ctx.model_dump_json()
    reconstructed = IntelligenceContext.model_validate_json(payload)
    assert reconstructed.contract_version == ctx.contract_version
    assert reconstructed.decision.state == ctx.decision.state
