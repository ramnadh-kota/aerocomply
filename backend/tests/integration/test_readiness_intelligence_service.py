import uuid

import pytest

from app.core.errors import NotFoundError
from app.models.compliance import ComplianceState
from app.models.finding import FindingSeverity
from app.models.organization import Organization
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.compliance import (
    ComplianceObligationCreateRequest,
    ComplianceObligationUpdateRequest,
    RegulatoryRequirementCreateRequest,
)
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    compliance_service,
    drone_service,
    finding_service,
    work_order_service,
)
from app.services.compliance import obligation_service
from app.services.intelligence import readiness_intelligence_service


def _create_org(db_session):
    org = Organization(name=f"Readiness Test Org {uuid.uuid4().hex[:8]}")
    db_session.add(org)
    db_session.flush()
    return org.id


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N100RI", msn="MSN-RI-1", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def _create_drone(db_session, org_id, **overrides):
    data = dict(
        registration="DRN-RI-1",
        manufacturer=None,
        model=None,
        serial_number=None,
        facility_id=None,
    )
    data.update(overrides)
    return drone_service.create_drone(
        db_session, organization_id=org_id, actor_user_id=None, **data
    )


def test_asset_with_no_compliance_obligations_is_unknown_not_ready(db_session):
    # Mirrors app/services/aerospace_state_service.py's own documented rule:
    # zero ComplianceObligation rows means "cannot confirm compliance state",
    # not "confirmed clean" -- so a brand-new aircraft is UNKNOWN, never READY.
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)

    result = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.readiness_state == "UNKNOWN"
    assert result.blockers == []


def test_critical_finding_blocks_via_aerospace_state(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N100RI2", msn="MSN-RI-2")
    finding_service.create_finding(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        title="Cracked spar",
        description="Structural crack found during inspection",
        severity=FindingSeverity.CRITICAL,
        aircraft_id=aircraft.id,
    )

    result = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.readiness_state == "BLOCKED"
    assert any(b.source_domain == "AEROSPACE_STATE" for b in result.blockers)
    assert result.contributing_factors["critical_findings_count"] == 1


def test_incomplete_task_blocks_via_open_work_order(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id, registration="N100RI3", msn="MSN-RI-3")
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-RI-1"),
    )
    work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Torque check"),
    )

    result = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.readiness_state == "BLOCKED"
    assert any(b.source_domain == "WORK_ORDER" for b in result.blockers)
    assert result.contributing_factors["blocked_work_orders_count"] == 1


def test_drone_without_battery_blocks_via_deployment(db_session):
    org_id = uuid.uuid4()
    drone = _create_drone(db_session, org_id)

    result = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org_id, asset_id=drone.id
    )

    assert result.readiness_state == "BLOCKED"
    assert any(b.source_domain == "DEPLOYMENT" for b in result.blockers)


def test_blocked_obligation_never_collapses_to_ready(db_session):
    org_id = _create_org(db_session)
    aircraft = _create_aircraft(db_session, org_id, registration="N100RI4", msn="MSN-RI-4")
    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            requirement_number="AD-RI-1",
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

    result = readiness_intelligence_service.get_asset_readiness_intelligence(
        db_session, organization_id=org_id, asset_id=aircraft.asset_id
    )

    assert result.readiness_state != "READY"


def test_readiness_intelligence_is_tenant_scoped(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_a, registration="N100RI5", msn="MSN-RI-5")

    with pytest.raises(NotFoundError):
        readiness_intelligence_service.get_asset_readiness_intelligence(
            db_session, organization_id=org_b, asset_id=aircraft.asset_id
        )
