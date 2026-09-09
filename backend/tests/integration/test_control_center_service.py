import datetime
import uuid

from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.aog_event import AogEventCreateRequest
from app.schemas.deferred_item import DeferredItemCreateRequest
from app.schemas.part import PartCreateRequest
from app.schemas.part_requirement import PartRequirementCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    aog_service,
    control_center_service,
    deferred_item_service,
    part_requirement_service,
    part_service,
    work_order_service,
)


def _create_aircraft(db_session, org_id, **overrides):
    data = dict(registration="N1000AC", msn="MSN-100", aircraft_type="B737")
    data.update(overrides)
    return aircraft_service.create_aircraft(
        db_session, organization_id=org_id, payload=AircraftCreateRequest(**data)
    )


def test_aircraft_with_no_activity_is_operational(db_session):
    org_id = uuid.uuid4()
    _create_aircraft(db_session, org_id)

    rows = control_center_service.get_fleet_rows(db_session, organization_id=org_id)
    assert len(rows) == 1
    assert rows[0].operational_status == "OPERATIONAL"
    assert rows[0].open_work_orders == 0


def test_aircraft_with_open_work_order_is_under_maintenance(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-9000"),
    )

    rows = control_center_service.get_fleet_rows(db_session, organization_id=org_id)
    assert rows[0].operational_status == "UNDER_MAINTENANCE"
    assert rows[0].open_work_orders == 1


def test_aircraft_with_active_aog_overrides_under_maintenance(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-9001"),
    )
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft.id),
    )

    rows = control_center_service.get_fleet_rows(db_session, organization_id=org_id)
    assert rows[0].operational_status == "AOG"
    assert rows[0].active_aog_event_id is not None


def test_recovered_aog_does_not_count_as_active(db_session):
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

    rows = control_center_service.get_fleet_rows(db_session, organization_id=org_id)
    assert rows[0].operational_status == "OPERATIONAL"
    assert rows[0].active_aog_event_id is None


def test_open_deferred_items_counted(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    deferred_item_service.create_deferred_item(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=DeferredItemCreateRequest(
            aircraft_id=aircraft.id, description="APU inop", opened_at=datetime.date.today()
        ),
    )

    rows = control_center_service.get_fleet_rows(db_session, organization_id=org_id)
    assert rows[0].open_deferred_items == 1


def test_part_shortage_counted_on_open_work_order(db_session):
    org_id = uuid.uuid4()
    aircraft = _create_aircraft(db_session, org_id)
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=None,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-9002"),
    )
    part = part_service.create_part(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartCreateRequest(
            part_number="PN-9000", description="Fuel valve", quantity_on_hand=0
        ),
    )
    part_requirement_service.create_part_requirement(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=PartRequirementCreateRequest(
            work_order_id=work_order.id, part_id=part.id, required_quantity=1
        ),
    )

    rows = control_center_service.get_fleet_rows(db_session, organization_id=org_id)
    assert rows[0].open_part_shortages == 1


def test_summary_aggregates_across_fleet(db_session):
    org_id = uuid.uuid4()
    aircraft_a = _create_aircraft(db_session, org_id, registration="N1001AC")
    _create_aircraft(db_session, org_id, registration="N1002AC", msn="MSN-101")
    aog_service.declare_aog(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        payload=AogEventCreateRequest(aircraft_id=aircraft_a.id),
    )

    summary = control_center_service.get_summary(db_session, organization_id=org_id)
    assert summary.total_aircraft == 2
    assert summary.aog == 1
    assert summary.operational == 1


def test_fleet_scoped_to_tenant(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    _create_aircraft(db_session, org_a)

    rows_a = control_center_service.get_fleet_rows(db_session, organization_id=org_a)
    rows_b = control_center_service.get_fleet_rows(db_session, organization_id=org_b)
    assert len(rows_a) == 1
    assert rows_b == []
