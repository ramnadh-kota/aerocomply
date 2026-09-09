import uuid

from sqlalchemy.orm import Session

from app.models.aog_event import AogEventStatus
from app.models.part_requirement import PartRequirementStatus
from app.schemas.control_center import ControlCenterAircraftRow, ControlCenterSummary
from app.services import (
    aircraft_service,
    aog_service,
    deferred_item_service,
    part_requirement_service,
    work_order_service,
)

# Every count here traces to a real backend record from a domain already
# built (M2 work orders, M3.9 AOG, M3.11 deferred items, M3.3 part
# requirements). This deliberately does NOT attempt the frontend's fuller
# getControlTowerFleet (frontend/lib/mock/ai/analytics.ts), which also
# factors in a Defect model, an AircraftRiskAssessment model, and an
# upcoming-maintenance-events projection — none of which have a backend
# equivalent yet. Adding fake defect/risk numbers to make this row "look"
# as rich as the frontend one would be exactly the fabrication this
# session has been avoiding throughout M3.
_OPEN_WORK_ORDER_STATUSES_EXCLUDED = {"COMPLETED"}


def _open_work_orders_for_aircraft(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> list:
    all_work_orders = work_order_service.list_work_orders(db, organization_id=organization_id)
    return [
        wo
        for wo in all_work_orders
        if wo.aircraft_id == aircraft_id and wo.status not in _OPEN_WORK_ORDER_STATUSES_EXCLUDED
    ]


def _open_part_shortage_count(
    db: Session, *, organization_id: uuid.UUID, work_order_ids: list[uuid.UUID]
) -> int:
    count = 0
    for work_order_id in work_order_ids:
        requirements = part_requirement_service.list_part_requirements_for_work_order(
            db, organization_id=organization_id, work_order_id=work_order_id
        )
        count += sum(1 for r in requirements if r.status == PartRequirementStatus.SHORT)
    return count


def get_fleet_rows(
    db: Session, *, organization_id: uuid.UUID
) -> list[ControlCenterAircraftRow]:
    aircraft_list = aircraft_service.list_aircraft(db, organization_id=organization_id)
    aog_events = aog_service.list_aog_events(db, organization_id=organization_id)
    active_aog_by_aircraft = {
        event.aircraft_id: event.id
        for event in aog_events
        if event.status in (AogEventStatus.DECLARED, AogEventStatus.IN_RECOVERY)
    }

    rows: list[ControlCenterAircraftRow] = []
    for aircraft in aircraft_list:
        open_wos = _open_work_orders_for_aircraft(
            db, organization_id=organization_id, aircraft_id=aircraft.id
        )
        open_deferred = deferred_item_service.list_deferred_items_for_aircraft(
            db, organization_id=organization_id, aircraft_id=aircraft.id, open_only=True
        )
        shortage_count = _open_part_shortage_count(
            db, organization_id=organization_id, work_order_ids=[wo.id for wo in open_wos]
        )
        active_aog_id = active_aog_by_aircraft.get(aircraft.id)

        if active_aog_id is not None:
            operational_status = "AOG"
        elif open_wos:
            operational_status = "UNDER_MAINTENANCE"
        else:
            operational_status = "OPERATIONAL"

        rows.append(
            ControlCenterAircraftRow(
                aircraft_id=aircraft.id,
                registration=aircraft.registration,
                operational_status=operational_status,
                open_work_orders=len(open_wos),
                open_deferred_items=len(open_deferred),
                open_part_shortages=shortage_count,
                active_aog_event_id=active_aog_id,
            )
        )
    return rows


def get_summary(db: Session, *, organization_id: uuid.UUID) -> ControlCenterSummary:
    rows = get_fleet_rows(db, organization_id=organization_id)
    return ControlCenterSummary(
        total_aircraft=len(rows),
        operational=sum(1 for r in rows if r.operational_status == "OPERATIONAL"),
        under_maintenance=sum(1 for r in rows if r.operational_status == "UNDER_MAINTENANCE"),
        aog=sum(1 for r in rows if r.operational_status == "AOG"),
        open_work_orders_total=sum(r.open_work_orders for r in rows),
        open_deferred_items_total=sum(r.open_deferred_items for r in rows),
        open_part_shortages_total=sum(r.open_part_shortages for r in rows),
    )
