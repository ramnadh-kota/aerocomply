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
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    aog_service,
    compliance_service,
    drone_service,
    finding_service,
    work_order_service,
)
from app.services.compliance import obligation_service
from app.services.intelligence import recommendation_service


def _create_org(db_session):
    org = Organization(name=f"Recommendation Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N500RE", msn="MSN-RE-1", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def _create_drone(db_session, org_id, **overrides):
    data = dict(
        registration="DRN-RE-1",
        manufacturer=None,
        model=None,
        serial_number=None,
        facility_id=None,
    )
    data.update(overrides)
    return drone_service.create_drone(
        db_session, organization_id=org_id, actor_user_id=None, **data
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


# 1. NOMINAL / no-action scenario
def test_nominal_asset_yields_no_action_required_recommendation(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id)
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-RE-1"
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.recommendation_state == "NO_ACTION_REQUIRED"
    assert len(result.items) == 1
    assert result.items[0].action_category == "NO_ACTION_REQUIRED"
    assert result.blockers == []


# 2. DEGRADED / monitor scenario
def test_degraded_state_yields_monitor_recommendation(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE2", msn="MSN-RE-2")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-RE-2"
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

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.recommendation_state == "MONITOR"
    assert len(result.items) >= 1
    assert all(item.action_category == "MONITOR_CONDITION" for item in result.items)


# 3. RESTRICTED / blocker-resolution scenario, 14. authoritative required_action
#    propagation, 15. resolution-condition propagation, 16. source traceability
def test_restricted_state_surfaces_authoritative_required_action(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE3", msn="MSN-RE-3")
    obligation = _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-RE-3"
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.recommendation_state == "ACTION_REQUIRED"
    # NON_COMPLIANT_OBLIGATION is the blocker under test; aerospace_state_service
    # also raises a MISSING_EVIDENCE blocker for the same obligation regardless of
    # evidence_requirements being unset (a pre-existing D2.1 quirk, not modified
    # here -- see docs/DEVELOPER_2_D2_2_RECOMMENDATION_ENGINE.md "Known
    # limitations"). Both are legitimately preserved, not discarded.
    assert len(result.items) == 2
    non_compliant_item = next(
        item
        for item in result.items
        if item.source_blocker and "NON_COMPLIANT_OBLIGATION" in item.source_blocker.category
    )
    assert non_compliant_item.action_category == "PERFORM_REQUIRED_ACTION"
    assert non_compliant_item.action  # copied verbatim from the source blocker's required_action
    assert non_compliant_item.source_blocker.source_domain == "AEROSPACE_STATE"
    assert non_compliant_item.source_blocker.related_record_id == obligation.id
    assert non_compliant_item.source_blocker.related_record_type == "ComplianceObligation"


# 4. GROUNDED_INTEL scenario
def test_grounded_intel_yields_immediate_action_required_recommendation(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE4", msn="MSN-RE-4")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.recommendation_state == "IMMEDIATE_ACTION_REQUIRED"
    assert result.priority_level == "CRITICAL"
    assert len(result.items) >= 1


# 5. UNKNOWN_INTEL scenario, 6. UNKNOWN readiness, 7. UNKNOWN risk,
#    8. INSUFFICIENT_DATA decision
def test_unknown_intel_yields_insufficient_data_recommendation(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.recommendation_state == "INSUFFICIENT_DATA"
    assert result.readiness_state == "UNKNOWN"
    assert result.risk_level == "UNKNOWN"
    assert len(result.items) >= 1
    assert all(item.action_category == "OBTAIN_MISSING_INFORMATION" for item in result.items)
    # UNKNOWN must never become a positive/nominal conclusion.
    assert result.recommendation_state not in (
        "NO_ACTION_REQUIRED",
        "MONITOR",
        "ACTION_REQUIRED",
        "IMMEDIATE_ACTION_REQUIRED",
    )
    for item in result.items:
        assert "ready" not in item.action.lower() or "insufficient" in item.action.lower()
        assert item.action not in ("Aircraft is ready.", "Continue operation.", "Low risk.")


# 9. single blocker (covered above), 10. multiple blockers
def test_multiple_blockers_are_all_preserved_and_ordered(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE5", msn="MSN-RE-5")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-RE-5"
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-RE-1"),
    )
    work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Torque check"),
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert len(result.items) >= 2
    domains = [item.source_blocker.source_domain for item in result.items if item.source_blocker]
    assert "AEROSPACE_STATE" in domains
    assert "WORK_ORDER" in domains
    # Deterministic ordering: AEROSPACE_STATE items precede WORK_ORDER items.
    first_work_order_index = domains.index("WORK_ORDER")
    assert all(d == "AEROSPACE_STATE" for d in domains[:first_work_order_index])


# 11. missing evidence -- deployment blocker with no authoritative action falls
#     back to RESOLVE_BLOCKER using the blocker's own description
def test_deployment_blocker_without_authoritative_action_falls_back_to_resolve_blocker(db_session):
    # A COMPLIANT obligation is required so aerospace_intelligence_status is
    # NOMINAL (not UNKNOWN_INTEL from zero obligations), which keeps risk_level
    # a concrete value instead of UNKNOWN -- otherwise decision_state would be
    # INSUFFICIENT_DATA (risk UNKNOWN) rather than ACTION_REQUIRED, and the
    # deployment blocker (present either way) would never surface as an item.
    org_id = _create_org(db_session)
    drone = _create_drone(db_session, org_id)
    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            requirement_number="AD-RE-11",
            title="Test AD",
            description="Test airworthiness directive",
        ),
    )
    obligation = obligation_service.create_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceObligationCreateRequest(requirement_id=requirement.id, asset_id=drone.id),
    )
    obligation_service.update_obligation(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        obligation_id=obligation.id,
        payload=ComplianceObligationUpdateRequest(status=ComplianceState.COMPLIANT.value),
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=drone.id
    )

    deployment_items = [
        item
        for item in result.items
        if item.source_blocker and item.source_blocker.source_domain == "DEPLOYMENT"
    ]
    assert deployment_items
    for item in deployment_items:
        assert item.action_category == "RESOLVE_BLOCKER"
        assert item.resolution_condition is None
        assert item.action == item.source_blocker.description


# 12. compliance blocker (covered above via NON_COMPLIANT case)
# 13. inspection/finding blocker
def test_critical_finding_blocker_is_surfaced_as_action_item(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE6", msn="MSN-RE-6")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.COMPLIANT.value, "AD-RE-6"
    )
    finding_service.create_finding(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        title="Cracked spar",
        description="Structural crack found during inspection",
        severity=FindingSeverity.CRITICAL,
        aircraft_id=aircraft.id,
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.recommendation_state in ("IMMEDIATE_ACTION_REQUIRED", "ACTION_REQUIRED")
    assert any(
        item.source_blocker and item.source_blocker.category.startswith("FINDING:")
        for item in result.items
    )


# 17. priority propagation, 18. decision propagation
def test_recommendation_propagates_priority_and_decision_context(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE7", msn="MSN-RE-7")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    result = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.priority_level == "CRITICAL"
    assert result.risk_level == "CRITICAL"
    assert result.readiness_state == "BLOCKED"


# 19. deterministic repeated execution
def test_recommendation_is_deterministic_across_repeated_calls(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N500RE8", msn="MSN-RE-8")
    _create_requirement_and_obligation(
        db_session, org_id, aircraft, ComplianceState.NON_COMPLIANT.value, "AD-RE-8"
    )

    first = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )
    second = recommendation_service.get_asset_recommendation(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert first.recommendation_state == second.recommendation_state
    assert len(first.items) == len(second.items)
    assert [i.action for i in first.items] == [i.action for i in second.items]


# 20. tenant isolation
def test_recommendation_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_a, registration="N500RE9", msn="MSN-RE-9")

    with pytest.raises(NotFoundError):
        recommendation_service.get_asset_recommendation(
            db_session, organization_id=org_b, asset_id=aircraft.asset_id
        )


# 22. invalid asset
def test_recommendation_invalid_asset_raises_not_found(db_session):
    org_id = uuid.uuid4()

    with pytest.raises(NotFoundError):
        recommendation_service.get_asset_recommendation(
            db_session, organization_id=org_id, asset_id=uuid.uuid4()
        )
