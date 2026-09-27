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
from app.services.intelligence import fleet_intelligence_service


def _create_org(db_session):
    org = Organization(name=f"Fleet Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N600FL", msn="MSN-FL-1", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def test_empty_org_yields_empty_fleet_summary(db_session):
    org_id = uuid.uuid4()

    result = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_id
    )

    assert result.total_assets == 0
    assert result.assets == []


def test_fleet_summary_includes_every_asset_with_real_intelligence(db_session):
    org_id = _create_org(db_session)
    aircraft1 = _create_aircraft(db_session, org_id, registration="N600FL2", msn="MSN-FL-2")
    aircraft2 = _create_aircraft(db_session, org_id, registration="N600FL3", msn="MSN-FL-3")

    for aircraft, req_num in [(aircraft1, "AD-FL-1"), (aircraft2, "AD-FL-2")]:
        requirement = compliance_service.create_requirement(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            payload=RegulatoryRequirementCreateRequest(
                authority="FAA", requirement_number=req_num, title="Test AD", description="Test AD"
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
            payload=ComplianceObligationUpdateRequest(status=ComplianceState.COMPLIANT.value),
        )

    result = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_id
    )

    assert result.total_assets == 2
    asset_ids = {a.asset_id for a in result.assets}
    assert aircraft1.asset_id in asset_ids
    assert aircraft2.asset_id in asset_ids
    for a in result.assets:
        assert a.readiness_state == "READY"
        assert a.risk_level == "LOW"
        assert a.decision_state == "NO_ACTION_REQUIRED"


def test_fleet_summary_surfaces_unknown_intel_without_collapsing(db_session):
    org_id = uuid.uuid4()
    _create_aircraft(db_session, org_id, registration="N600FL4", msn="MSN-FL-4")

    result = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_id
    )

    assert result.total_assets == 1
    asset = result.assets[0]
    assert asset.readiness_state == "UNKNOWN"
    assert asset.risk_level == "UNKNOWN"
    assert asset.decision_state == "INSUFFICIENT_DATA"


def test_fleet_summary_surfaces_critical_grounded_asset(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N600FL5", msn="MSN-FL-5")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    result = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_id
    )

    asset = next(a for a in result.assets if a.asset_id == aircraft.asset_id)
    assert asset.priority_level == "CRITICAL"
    assert asset.decision_state == "IMMEDIATE_ACTION_REQUIRED"
    assert asset.blocker_count >= 1


def test_fleet_summary_preserves_blocker_traceability(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N600FL6", msn="MSN-FL-6")
    finding_service.create_finding(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        title="Cracked spar",
        description="Structural crack found during inspection",
        severity=FindingSeverity.CRITICAL,
        aircraft_id=aircraft.id,
    )

    result = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_id
    )

    asset = next(a for a in result.assets if a.asset_id == aircraft.asset_id)
    assert asset.blockers
    assert any(b.source_domain == "AEROSPACE_STATE" for b in asset.blockers)


def test_fleet_summary_is_tenant_scoped(db_session):
    org_a = _create_org(db_session)
    org_b = uuid.uuid4()
    _create_aircraft(db_session, org_a, registration="N600FL7", msn="MSN-FL-7")

    result_a = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_a
    )
    result_b = fleet_intelligence_service.get_fleet_intelligence_summary(
        db_session, organization_id=org_b
    )

    assert result_a.total_assets == 1
    assert result_b.total_assets == 0
