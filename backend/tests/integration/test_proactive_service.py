import datetime
import uuid

from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.compliance import (
    ComplianceAssessmentCreateRequest,
    RegulatoryRequirementCreateRequest,
)
from app.schemas.deferred_item import DeferredItemCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    aog_service,
    compliance_service,
    deferred_item_service,
    part_requirement_service,
    part_service,
    proactive_service,
    work_order_service,
)


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N2000PA", msn="MSN-PA-1", aircraft_type="A320")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def test_no_data_produces_no_alerts(db_session):
    org_id = uuid.uuid4()
    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    assert alerts == []


def test_aog_event_produces_critical_alert(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id, root_cause="Test root cause"),
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    aog_alerts = [a for a in alerts if a.category == "AOG"]
    assert len(aog_alerts) == 1
    assert aog_alerts[0].severity == "CRITICAL"
    assert "Test root cause" in aog_alerts[0].message


def test_recovered_aog_produces_no_alert(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    event = aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )
    aog_service.start_recovery(
        db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
    )
    aog_service.mark_recovered(
        db_session, organization_id=org_id, actor_user_id=None, event_id=event.id
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    assert [a for a in alerts if a.category == "AOG"] == []


def test_part_shortage_produces_alert(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-PA-1"),
    )
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(part_number="PN-PA-1", description="Valve", quantity_on_hand=0),
    )
    part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=1
        ),
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    shortage_alerts = [a for a in alerts if a.category == "PART_SHORTAGE"]
    assert len(shortage_alerts) == 1
    assert shortage_alerts[0].work_order_id == work_order.id


def test_release_blocker_produces_alert_for_incomplete_task(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-PA-2"),
    )
    from app.schemas.task import TaskCreateRequest

    work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Inspect panel"),
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    blocker_alerts = [a for a in alerts if a.category == "RELEASE_BLOCKER"]
    assert len(blocker_alerts) == 1
    assert "TASK_EXECUTION" in blocker_alerts[0].message


def test_overdue_deferred_item_produces_critical_alert(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    deferred_item_service.create_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=DeferredItemCreateRequest(
            aircraft_id=aircraft.id,
            description="APU inop",
            opened_at=datetime.date.today() - datetime.timedelta(days=10),
            due_at=datetime.date.today() - datetime.timedelta(days=1),
        ),
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    deferred_alerts = [a for a in alerts if a.category == "DEFERRED_MEL"]
    assert len(deferred_alerts) == 1
    assert deferred_alerts[0].severity == "CRITICAL"


def test_deferred_item_without_due_date_produces_no_alert(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    deferred_item_service.create_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=DeferredItemCreateRequest(
            aircraft_id=aircraft.id,
            description="Unknown due date item",
            opened_at=datetime.date.today(),
        ),
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    assert [a for a in alerts if a.category == "DEFERRED_MEL"] == []


def test_non_compliant_assessment_produces_alert(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    requirement = compliance_service.create_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=RegulatoryRequirementCreateRequest(
            authority="FAA",
            requirement_number="AD-PA-1",
            title="Test AD",
            description="Test description",
        ),
    )
    compliance_service.create_assessment(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft.id,
            requirement_id=requirement.id,
            status="NON_COMPLIANT",
            evaluated_at=datetime.date.today(),
        ),
    )

    alerts = proactive_service.get_proactive_alerts(db_session, organization_id=org_id)
    compliance_alerts = [a for a in alerts if a.category == "COMPLIANCE"]
    assert len(compliance_alerts) == 1


def test_alerts_scoped_to_tenant(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_a)
    aog_service.declare_aog(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    alerts_b = proactive_service.get_proactive_alerts(db_session, organization_id=org_b)
    assert alerts_b == []


def test_daily_brief_counts_and_top_priorities(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    brief = proactive_service.get_daily_brief(db_session, organization_id=org_id)
    assert brief.critical_count == 1
    assert brief.total_count == 1
    assert len(brief.top_priorities) == 1
    assert brief.not_implemented  # explicit, non-empty — honest about coverage gaps
