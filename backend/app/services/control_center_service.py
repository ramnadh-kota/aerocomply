import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.aog_event import AogEventStatus
from app.models.asset import Asset
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.battery import Battery
from app.models.component import Component
from app.models.installation_history import ComponentInstallation
from app.models.finding import Finding, FindingStatus
from app.models.flight import Flight
from app.models.inspection_requirement import (
    InspectionRequirement,
    InspectionRequirementStatus,
)
from app.models.mission import Mission, MissionStatus
from app.models.part_requirement import PartRequirementStatus
from app.models.work_order import WorkOrder
from app.schemas.control_center import (
    ControlCenterAircraftRow,
    ControlCenterAttentionItem,
    ControlCenterDailyBrief,
    ControlCenterFleetHealth,
    ControlCenterFleetOperationRow,
    ControlCenterOperationalActivity,
    ControlCenterSummary,
    OperationalTimelineEvent,
)
from app.services import (
    aircraft_service,
    aog_service,
    asset_service,
    deferred_item_service,
    flight_service,
    part_requirement_service,
)

_OPEN_WORK_ORDER_STATUSES_EXCLUDED = {"COMPLETED", "CLOSED", "CANCELLED"}

_STATE_TO_LEGACY_STATUS = {
    "AOG": "AOG",
    "MAINTENANCE": "UNDER_MAINTENANCE",
    "UNDER_INSPECTION": "UNDER_MAINTENANCE",
    "GROUNDED": "UNDER_MAINTENANCE",
    "RETIRED": "UNDER_MAINTENANCE",
    "INACTIVE": "UNDER_MAINTENANCE",
    "AVAILABLE": "OPERATIONAL",
    "IN_MISSION": "OPERATIONAL",
}


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

    open_work_order_rows = list(
        db.execute(
            select(WorkOrder).where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.deleted_at.is_(None),
                WorkOrder.status.notin_(_OPEN_WORK_ORDER_STATUSES_EXCLUDED),
            )
        ).scalars().all()
    )
    open_wos_by_aircraft: dict[uuid.UUID, list[WorkOrder]] = {}
    for wo in open_work_order_rows:
        if wo.aircraft_id is not None:
            open_wos_by_aircraft.setdefault(wo.aircraft_id, []).append(wo)

    all_open_wo_ids = [wo.id for wo in open_work_order_rows]
    shortage_count_by_wo_id: dict[uuid.UUID, int] = {}
    for wo_id in all_open_wo_ids:
        requirements = part_requirement_service.list_part_requirements_for_work_order(
            db, organization_id=organization_id, work_order_id=wo_id
        )
        shortage_count_by_wo_id[wo_id] = sum(
            1 for r in requirements if r.status == PartRequirementStatus.SHORT
        )

    rows: list[ControlCenterAircraftRow] = []
    for aircraft in aircraft_list:
        open_wos = open_wos_by_aircraft.get(aircraft.id, [])
        open_deferred = deferred_item_service.list_deferred_items_for_aircraft(
            db, organization_id=organization_id, aircraft_id=aircraft.id, open_only=True
        )
        shortage_count = sum(shortage_count_by_wo_id.get(wo.id, 0) for wo in open_wos)
        active_aog_id = active_aog_by_aircraft.get(aircraft.id)

        if aircraft.asset_id is not None:
            asset = asset_service.get_asset(
                db, organization_id=organization_id, asset_id=aircraft.asset_id
            )
            state = asset_service.compute_operational_state(
                db, organization_id=organization_id, asset=asset
            )
            operational_status = _STATE_TO_LEGACY_STATUS[state]
        elif active_aog_id is not None:
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

    # Full 8-value operational-state distribution across every asset in the org
    assets = list(
        db.execute(
            select(Asset).where(Asset.organization_id == organization_id, Asset.deleted_at.is_(None))
        ).scalars().all()
    )
    operational_states: dict[str, int] = {
        "AVAILABLE": 0,
        "IN_MISSION": 0,
        "UNDER_INSPECTION": 0,
        "MAINTENANCE": 0,
        "GROUNDED": 0,
        "AOG": 0,
        "INACTIVE": 0,
        "RETIRED": 0,
    }
    asset_class_counts: dict[str, int] = {}
    ready_count = 0
    restricted_count = 0
    maintenance_due_count = 0

    asset_state_map: dict[uuid.UUID, str] = {}
    for asset in assets:
        state = asset_service.compute_operational_state(
            db, organization_id=organization_id, asset=asset
        )
        operational_states[state] = operational_states.get(state, 0) + 1
        asset_class_counts[asset.asset_type] = asset_class_counts.get(asset.asset_type, 0) + 1
        asset_state_map[asset.id] = state

        if state in ("AVAILABLE", "IN_MISSION"):
            ready_count += 1
        elif state in ("GROUNDED", "AOG", "MAINTENANCE", "UNDER_INSPECTION"):
            restricted_count += 1
        if state in ("MAINTENANCE", "UNDER_INSPECTION"):
            maintenance_due_count += 1

    # 1. Operational Activity (Flights, Hours, Cycles, Active Missions)
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = today_start - timedelta(days=today_start.weekday())

    flights_all = list(
        db.execute(
            select(Flight).where(Flight.organization_id == organization_id)
        ).scalars().all()
    )

    flights_today = sum(1 for f in flights_all if f.flown_at >= today_start)
    flights_this_week = sum(1 for f in flights_all if f.flown_at >= week_start)
    total_flight_minutes_raw = sum(f.duration_minutes for f in flights_all)
    total_flight_cycles_raw = sum(f.cycles for f in flights_all)

    # Baselines integration
    baselines = list(
        db.execute(
            select(AssetHistoricalBaseline).where(
                AssetHistoricalBaseline.organization_id == organization_id,
                AssetHistoricalBaseline.is_active.is_(True),
            )
        ).scalars().all()
    )
    baseline_hours_sum = sum(b.flight_hours for b in baselines)
    baseline_cycles_sum = sum(b.flight_cycles for b in baselines)

    total_flight_hours = round(baseline_hours_sum + (total_flight_minutes_raw / 60.0), 1)
    total_cycles = baseline_cycles_sum + total_flight_cycles_raw

    active_missions_count = db.execute(
        select(func.count(Mission.id)).where(
            Mission.organization_id == organization_id,
            Mission.status == MissionStatus.IN_PROGRESS,
        )
    ).scalar_one()

    operational_activity = ControlCenterOperationalActivity(
        flights_today=flights_today,
        flights_this_week=flights_this_week,
        total_flight_hours=total_flight_hours,
        total_cycles=total_cycles,
        total_flights=len(flights_all),
        active_missions=active_missions_count,
    )

    # 2. Attention Required Items (Prioritized from live domain state)
    attention_items: list[ControlCenterAttentionItem] = []

    # Open Findings (Critical & High first)
    open_findings = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.status == FindingStatus.OPEN,
            )
        ).scalars().all()
    )
    for fnd in open_findings:
        prio = "CRITICAL" if fnd.severity == "CRITICAL" else ("HIGH" if fnd.severity == "HIGH" else "MEDIUM")
        asset_reg = None
        asset_type = None
        if fnd.asset_id:
            asset_obj = next((a for a in assets if a.id == fnd.asset_id), None)
            if asset_obj:
                asset_reg = asset_obj.registration
                asset_type = asset_obj.asset_type

        attention_items.append(
            ControlCenterAttentionItem(
                id=f"fnd-{fnd.id}",
                asset_id=fnd.asset_id,
                registration=asset_reg,
                asset_type=asset_type,
                priority=prio,
                category="FINDING",
                title=f"Open Finding: {fnd.title}",
                reason=f"{fnd.severity} severity finding discovered on {fnd.discovered_at.strftime('%Y-%m-%d') if fnd.discovered_at else 'recent inspection'}.",
                blocking_condition=f"Finding #{str(fnd.id)[:8]} ({fnd.severity})",
                recommended_action="Investigate defect, determine root cause, and upload corrective action disposition.",
                link_href=f"/findings/{fnd.id}",
            )
        )

    # Open Work Orders (Overdue, Awaiting Parts, Critical)
    open_work_orders = list(
        db.execute(
            select(WorkOrder).where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.deleted_at.is_(None),
                WorkOrder.status.notin_(_OPEN_WORK_ORDER_STATUSES_EXCLUDED),
            )
        ).scalars().all()
    )
    for wo in open_work_orders:
        is_overdue = wo.due_at is not None and wo.due_at.date() < now.date() if isinstance(wo.due_at, datetime) else False
        is_critical_priority = wo.priority == "CRITICAL"
        prio = "CRITICAL" if (is_overdue or is_critical_priority) else ("HIGH" if wo.priority == "HIGH" else "MEDIUM")
        asset_reg = None
        asset_type = None
        if wo.asset_id:
            asset_obj = next((a for a in assets if a.id == wo.asset_id), None)
            if asset_obj:
                asset_reg = asset_obj.registration
                asset_type = asset_obj.asset_type

        if is_overdue or is_critical_priority or prio in ("CRITICAL", "HIGH"):
            attention_items.append(
                ControlCenterAttentionItem(
                    id=f"wo-{wo.id}",
                    asset_id=wo.asset_id,
                    registration=asset_reg,
                    asset_type=asset_type,
                    priority=prio,
                    category="MAINTENANCE",
                    title=f"Maintenance Task: {wo.work_order_number or wo.title}",
                    reason=f"Work order is {wo.status}" + (f", overdue since {wo.due_at.strftime('%Y-%m-%d')}" if is_overdue else "."),
                    blocking_condition=f"Work Order #{wo.work_order_number or str(wo.id)[:8]}",
                    recommended_action="Assign maintenance technician, verify material availability, and complete task.",
                    link_href=f"/maintenance/work-orders/{wo.id}",
                )
            )

    # Incomplete / Pending Inspections
    pending_inspections = list(
        db.execute(
            select(InspectionRequirement).where(
                InspectionRequirement.organization_id == organization_id,
                InspectionRequirement.status == InspectionRequirementStatus.PENDING,
            )
        ).scalars().all()
    )
    for insp in pending_inspections:
        attention_items.append(
            ControlCenterAttentionItem(
                id=f"insp-{insp.id}",
                asset_id=None,
                registration=None,
                asset_type=None,
                priority="HIGH",
                category="INSPECTION",
                title=f"Inspection Pending: #{str(insp.id)[:8]}",
                reason="Inspection requirement pending authorized sign-off for release to service.",
                blocking_condition=f"Inspection #{str(insp.id)[:8]}",
                recommended_action="Perform required airworthiness inspection checklist and record sign-off.",
                link_href="/maintenance/inspections",
            )
        )

    # Battery thresholds for Drone fleets
    batteries = list(
        db.execute(
            select(Battery).where(
                Battery.organization_id == organization_id,
            )
        ).scalars().all()
    )
    for bat in batteries:
        if bat.status in ("CRITICAL", "SERVICE_DUE") or (bat.health_percent is not None and bat.health_percent < 70):
            asset_obj = next((a for a in assets if a.id == bat.asset_id), None) if bat.asset_id else None
            prio = "CRITICAL" if bat.status == "CRITICAL" else "HIGH"
            attention_items.append(
                ControlCenterAttentionItem(
                    id=f"bat-{bat.id}",
                    asset_id=bat.asset_id,
                    registration=asset_obj.registration if asset_obj else None,
                    asset_type="DRONE",
                    priority=prio,
                    category="BATTERY",
                    title=f"Battery Health Degradation: {bat.serial_number or 'Battery'}",
                    reason=f"Battery status is {bat.status} (Health: {bat.health_percent or 'N/A'}%, Cycles: {bat.cycle_count}).",
                    blocking_condition=f"Battery #{bat.serial_number or str(bat.id)[:8]} ({bat.status})",
                    recommended_action="Quarantine battery pack and install replacement battery module.",
                    link_href="/drones",
                )
            )

    # Sort attention items: CRITICAL first, then HIGH, then MEDIUM, then LOW
    _prio_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    attention_items.sort(key=lambda x: _prio_rank.get(x.priority, 99))

    # 3. Fleet Health Model
    fleet_health = ControlCenterFleetHealth(
        total_assets=len(assets),
        ready_count=ready_count,
        restricted_count=restricted_count,
        maintenance_due_count=maintenance_due_count,
        grounded_count=(operational_states.get("GROUNDED", 0) + operational_states.get("AOG", 0)),
        available_count=operational_states.get("AVAILABLE", 0),
        in_mission_count=operational_states.get("IN_MISSION", 0),
        unknown_count=operational_states.get("INACTIVE", 0) + operational_states.get("RETIRED", 0),
        asset_class_counts=asset_class_counts,
    )

    # 4. Daily Operational Brief
    key_bullets = []
    if restricted_count > 0:
        key_bullets.append(f"{restricted_count} asset(s) are currently restricted or grounded.")
    if len(open_findings) > 0:
        key_bullets.append(f"{len(open_findings)} open finding(s) require engineering disposition.")
    if len(open_work_orders) > 0:
        key_bullets.append(f"{len(open_work_orders)} active work order(s) in progress across the fleet.")
    if len(pending_inspections) > 0:
        key_bullets.append(f"{len(pending_inspections)} inspection requirement(s) awaiting verification.")
    if not key_bullets:
        key_bullets.append("All fleet assets are nominal, compliant, and ready for flight operations.")

    headline = (
        f"{len(attention_items)} priority item(s) require operational attention today."
        if attention_items
        else "Fleet operations are nominal with zero active blockers."
    )

    daily_brief = ControlCenterDailyBrief(
        date_str=now.strftime("%d %B %Y"),
        total_assets=len(assets),
        ready_assets=ready_count,
        attention_required_count=len(attention_items),
        restricted_assets=restricted_count,
        maintenance_due_count=len(open_work_orders),
        pending_inspections_count=len(pending_inspections),
        open_findings_count=len(open_findings),
        summary_headline=headline,
        key_bullet_points=key_bullets,
        generated_at=now,
    )

    readiness_dist = {
        "READY": ready_count,
        "BLOCKED": restricted_count,
        "UNKNOWN": len(assets) - (ready_count + restricted_count),
    }

    compliance_dist = {
        "COMPLIANT": ready_count,
        "REVIEW_REQUIRED": len(open_findings),
        "NON_COMPLIANT": restricted_count if len(open_findings) > 0 else 0,
        "INSUFFICIENT_DATA": 0,
    }

    return ControlCenterSummary(
        total_aircraft=len(rows),
        operational=sum(1 for r in rows if r.operational_status == "OPERATIONAL"),
        under_maintenance=sum(1 for r in rows if r.operational_status == "UNDER_MAINTENANCE"),
        aog=sum(1 for r in rows if r.operational_status == "AOG"),
        open_work_orders_total=sum(r.open_work_orders for r in rows),
        open_deferred_items_total=sum(r.open_deferred_items for r in rows),
        open_part_shortages_total=sum(r.open_part_shortages for r in rows),
        total_assets=len(assets),
        operational_states=operational_states,
        fleet_health=fleet_health,
        operational_activity=operational_activity,
        attention_items=attention_items[:20],  # top 20 prioritized
        daily_brief=daily_brief,
        readiness_distribution=readiness_dist,
        compliance_distribution=compliance_dist,
    )


def get_fleet_operations(
    db: Session, *, organization_id: uuid.UUID
) -> list[ControlCenterFleetOperationRow]:
    assets = list(
        db.execute(
            select(Asset)
            .where(Asset.organization_id == organization_id, Asset.deleted_at.is_(None))
            .order_by(Asset.created_at.desc())
        ).scalars().all()
    )

    # Batch open work orders and findings
    open_wos = list(
        db.execute(
            select(WorkOrder).where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.deleted_at.is_(None),
                WorkOrder.status.notin_(_OPEN_WORK_ORDER_STATUSES_EXCLUDED),
            )
        ).scalars().all()
    )
    open_wos_by_asset: dict[uuid.UUID, int] = {}
    for wo in open_wos:
        if wo.asset_id:
            open_wos_by_asset[wo.asset_id] = open_wos_by_asset.get(wo.asset_id, 0) + 1

    open_fnds = list(
        db.execute(
            select(Finding).where(
                Finding.organization_id == organization_id,
                Finding.status == FindingStatus.OPEN,
            )
        ).scalars().all()
    )
    open_fnds_by_asset: dict[uuid.UUID, int] = {}
    for f in open_fnds:
        if f.asset_id:
            open_fnds_by_asset[f.asset_id] = open_fnds_by_asset.get(f.asset_id, 0) + 1

    # Batch flights by asset
    flights = list(
        db.execute(
            select(Flight)
            .where(Flight.organization_id == organization_id)
            .order_by(Flight.flown_at.desc())
        ).scalars().all()
    )
    last_flight_by_asset: dict[uuid.UUID, datetime] = {}
    for f in flights:
        if f.asset_id and f.asset_id not in last_flight_by_asset:
            last_flight_by_asset[f.asset_id] = f.flown_at

    rows: list[ControlCenterFleetOperationRow] = []
    for asset in assets:
        op_state = asset_service.compute_operational_state(
            db, organization_id=organization_id, asset=asset
        )
        util = flight_service.get_utilization(
            db, organization_id=organization_id, asset_id=asset.id
        )

        wo_count = open_wos_by_asset.get(asset.id, 0)
        fnd_count = open_fnds_by_asset.get(asset.id, 0)
        blocker_count = (1 if op_state in ("GROUNDED", "AOG", "MAINTENANCE") else 0) + fnd_count

        readiness_state = "BLOCKED" if blocker_count > 0 else ("READY" if op_state in ("AVAILABLE", "IN_MISSION") else "UNKNOWN")
        risk_level = "CRITICAL" if op_state in ("AOG", "GROUNDED") else ("HIGH" if fnd_count > 0 else ("MEDIUM" if wo_count > 0 else "LOW"))
        priority_level = risk_level

        next_action = None
        if op_state == "AOG":
            next_action = "Initiate AOG recovery procedure"
        elif fnd_count > 0:
            next_action = "Investigate open finding & corrective action"
        elif wo_count > 0:
            next_action = "Execute pending work order task"
        elif op_state == "AVAILABLE":
            next_action = "Ready for mission / flight assignment"

        rows.append(
            ControlCenterFleetOperationRow(
                asset_id=asset.id,
                registration=asset.registration,
                asset_type=asset.asset_type,
                manufacturer=asset.manufacturer,
                model=asset.model,
                serial_number=asset.serial_number,
                lifecycle_status=asset.status,
                operational_state=op_state,
                readiness_state=readiness_state,
                risk_level=risk_level,
                priority_level=priority_level,
                total_flight_hours=round(util["total_minutes"] / 60.0, 1),
                total_cycles=util["total_cycles"],
                last_flight_at=last_flight_by_asset.get(asset.id),
                open_work_orders=wo_count,
                open_findings=fnd_count,
                active_blocker_count=blocker_count,
                next_action=next_action,
            )
        )

    return rows


def get_fleet_timeline(
    db: Session,
    *,
    organization_id: uuid.UUID,
    asset_id: uuid.UUID | None = None,
    event_type: str | None = None,
    limit: int = 50,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[OperationalTimelineEvent]:
    """Unified chronological operational timeline aggregating flight sorties,
    maintenance work orders, inspections, findings, component milestones, and baselines."""
    def _in_range(occurred_at: datetime) -> bool:
        if date_from is not None and occurred_at < date_from:
            return False
        if date_to is not None and occurred_at >= date_to:
            return False
        return True

    # Asset lookup map
    assets = list(
        db.execute(
            select(Asset).where(Asset.organization_id == organization_id, Asset.deleted_at.is_(None))
        ).scalars().all()
    )
    asset_map = {a.id: a for a in assets}

    events: list[OperationalTimelineEvent] = []

    # 1. Flights
    flight_stmt = select(Flight).where(Flight.organization_id == organization_id)
    if asset_id is not None:
        flight_stmt = flight_stmt.where(Flight.asset_id == asset_id)
    flights = list(db.execute(flight_stmt.order_by(Flight.flown_at.desc()).limit(limit)).scalars().all())
    for f in flights:
        a = asset_map.get(f.asset_id) if f.asset_id else None
        events.append(
            OperationalTimelineEvent(
                event_id=f"flight-{f.id}",
                event_type="FLIGHT_SORTIE",
                occurred_at=f.flown_at,
                title=f"Flight Flown: {f.flight_number or 'Sortie'} ({f.duration_minutes} min, {f.cycles} cyc)",
                description=f.notes or f"Operational flight from {f.origin or '—'} to {f.destination or '—'}.",
                actor=str(f.pilot_user_id) if f.pilot_user_id else None,
                entity_type="Flight",
                entity_id=str(f.id),
                asset_id=f.asset_id,
                asset_registration=a.registration if a else None,
                asset_type=a.asset_type if a else None,
                metadata={"duration_minutes": f.duration_minutes, "cycles": f.cycles, "source": f.source},
            )
        )

    # 2. Missions
    mission_stmt = select(Mission).where(Mission.organization_id == organization_id)
    if asset_id is not None:
        mission_stmt = mission_stmt.where(Mission.asset_id == asset_id)
    missions = list(db.execute(mission_stmt.order_by(Mission.created_at.desc()).limit(limit)).scalars().all())
    for m in missions:
        a = asset_map.get(m.asset_id) if m.asset_id else None
        events.append(
            OperationalTimelineEvent(
                event_id=f"mission-{m.id}",
                event_type="MISSION_CREATED",
                occurred_at=m.created_at,
                title=f"Mission Created: {m.purpose}",
                description=m.operating_area or "Mission operating area planned.",
                actor=str(m.pilot_user_id) if m.pilot_user_id else None,
                entity_type="Mission",
                entity_id=str(m.id),
                asset_id=m.asset_id,
                asset_registration=a.registration if a else None,
                asset_type=a.asset_type if a else None,
                metadata={"status": m.status},
            )
        )

    # 3. Work Orders
    wo_stmt = select(WorkOrder).where(WorkOrder.organization_id == organization_id, WorkOrder.deleted_at.is_(None))
    if asset_id is not None:
        wo_stmt = wo_stmt.where(WorkOrder.asset_id == asset_id)
    wos = list(db.execute(wo_stmt.order_by(WorkOrder.created_at.desc()).limit(limit)).scalars().all())
    for wo in wos:
        a = asset_map.get(wo.asset_id) if wo.asset_id else None
        events.append(
            OperationalTimelineEvent(
                event_id=f"wo-{wo.id}",
                event_type="WORK_ORDER_CREATED",
                occurred_at=wo.created_at,
                title=f"Work Order Created: {wo.work_order_number or wo.title}",
                description=wo.description or "Maintenance work order initiated.",
                actor=str(wo.created_by_user_id) if wo.created_by_user_id else None,
                entity_type="WorkOrder",
                entity_id=str(wo.id),
                asset_id=wo.asset_id,
                asset_registration=a.registration if a else None,
                asset_type=a.asset_type if a else None,
                metadata={"status": wo.status, "priority": wo.priority},
            )
        )
        if wo.completed_at:
            events.append(
                OperationalTimelineEvent(
                    event_id=f"wo-completed-{wo.id}",
                    event_type="WORK_ORDER_COMPLETED",
                    occurred_at=wo.completed_at,
                    title=f"Work Order Completed: {wo.work_order_number or wo.title}",
                    description="Maintenance task execution completed.",
                    actor=None,
                    entity_type="WorkOrder",
                    entity_id=str(wo.id),
                    asset_id=wo.asset_id,
                    asset_registration=a.registration if a else None,
                    asset_type=a.asset_type if a else None,
                    metadata={"status": wo.status},
                )
            )

    # 4. Findings
    fnd_stmt = select(Finding).where(Finding.organization_id == organization_id)
    if asset_id is not None:
        fnd_stmt = fnd_stmt.where(Finding.asset_id == asset_id)
    fnds = list(db.execute(fnd_stmt.order_by(Finding.discovered_at.desc()).limit(limit)).scalars().all())
    for f in fnds:
        a = asset_map.get(f.asset_id) if f.asset_id else None
        events.append(
            OperationalTimelineEvent(
                event_id=f"fnd-{f.id}",
                event_type="FINDING_CREATED",
                occurred_at=f.discovered_at,
                title=f"Finding Recorded: {f.title}",
                description=f.description or "Discrepancy identified during operational inspection.",
                actor=str(f.discovered_by_user_id) if f.discovered_by_user_id else None,
                entity_type="Finding",
                entity_id=str(f.id),
                asset_id=f.asset_id,
                asset_registration=a.registration if a else None,
                asset_type=a.asset_type if a else None,
                metadata={"severity": f.severity, "status": f.status},
            )
        )

    # 5. Component Installations
    comp_stmt = (
        select(ComponentInstallation, Component)
        .join(Component, ComponentInstallation.component_id == Component.id)
        .where(ComponentInstallation.organization_id == organization_id)
    )
    if asset_id is not None:
        comp_stmt = comp_stmt.where(ComponentInstallation.asset_id == asset_id)
    comp_rows = list(db.execute(comp_stmt.order_by(ComponentInstallation.installed_at.desc()).limit(limit)).all())
    for ci, c in comp_rows:
        a = asset_map.get(ci.asset_id) if ci.asset_id else None
        events.append(
            OperationalTimelineEvent(
                event_id=f"comp-inst-{ci.id}",
                event_type="COMPONENT_INSTALLATION",
                occurred_at=ci.installed_at,
                title=f"Component Installed: {c.name} ({c.component_type})",
                description=f"Serial: {c.serial_number or 'N/A'}, Mfr: {c.manufacturer or 'N/A'}",
                actor=str(ci.installed_by) if ci.installed_by else None,
                entity_type="Component",
                entity_id=str(c.id),
                asset_id=ci.asset_id,
                asset_registration=a.registration if a else None,
                asset_type=a.asset_type if a else None,
                metadata={"component_type": c.component_type},
            )
        )

    # 6. Baselines
    base_stmt = select(AssetHistoricalBaseline).where(AssetHistoricalBaseline.organization_id == organization_id)
    if asset_id is not None:
        base_stmt = base_stmt.where(AssetHistoricalBaseline.asset_id == asset_id)
    baselines = list(db.execute(base_stmt.order_by(AssetHistoricalBaseline.created_at.desc()).limit(limit)).scalars().all())
    for b in baselines:
        a = asset_map.get(b.asset_id) if b.asset_id else None
        events.append(
            OperationalTimelineEvent(
                event_id=f"base-{b.id}",
                event_type="HISTORICAL_BASELINE_SET",
                occurred_at=b.created_at,
                title=f"Historical Baseline Established: {b.flight_hours} FH / {b.flight_cycles} Cyc",
                description=f"Baseline accounting source: {b.source}. Effective as of {b.effective_at.strftime('%Y-%m-%d')}.",
                actor=str(b.created_by_user_id) if b.created_by_user_id else None,
                entity_type="AssetHistoricalBaseline",
                entity_id=str(b.id),
                asset_id=b.asset_id,
                asset_registration=a.registration if a else None,
                asset_type=a.asset_type if a else None,
                metadata={"flight_hours": b.flight_hours, "flight_cycles": b.flight_cycles, "source": b.source},
            )
        )

    # Filter & Sort
    if event_type:
        events = [e for e in events if e.event_type == event_type]
    events = [e for e in events if _in_range(e.occurred_at)]
    events.sort(key=lambda x: x.occurred_at, reverse=True)
    return events[:limit]
