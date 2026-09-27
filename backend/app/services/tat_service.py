"""Turnaround-time (TAT) status for a work order and across the fleet.

Operational TAT calculation based on WorkOrder.due_at:
- AT_RISK: due within 3 days
- DELAYED: due date has passed
- ON_TRACK: due in more than 3 days, or already completed/closed
- UNKNOWN: no due date recorded on the work order
"""

from datetime import UTC, datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.schemas.tat import FleetTatSummary, TatStatus

_NO_DUE_DATE_REASON = (
    "No due date is recorded for this work order yet. WorkOrder has no "
    "due_at field populated, so TAT status is reported as UNKNOWN."
)

_FLEET_REASON = (
    "No work orders carry a due date, so every work order is reported as "
    "UNKNOWN rather than fabricating a TAT status."
)


def calculate_tat_for_work_order(work_order: WorkOrder, now: datetime | None = None) -> TatStatus:
    if now is None:
        now = datetime.now(UTC)

    if work_order.due_at is None:
        return TatStatus(
            work_order_id=work_order.id,
            status="UNKNOWN",
            due_date=None,
            days_remaining=None,
            days_overdue=None,
            reason=_NO_DUE_DATE_REASON,
        )

    due_date_str = work_order.due_at.date().isoformat()
    now_date = now.date()
    due_date = work_order.due_at.date()
    delta_days = (due_date - now_date).days

    if work_order.status in (WorkOrderStatus.COMPLETED, WorkOrderStatus.CLOSED):
        return TatStatus(
            work_order_id=work_order.id,
            status="ON_TRACK",
            due_date=due_date_str,
            days_remaining=max(0, delta_days),
            days_overdue=None,
            reason="Work order is completed.",
        )

    if delta_days < 0:
        overdue_days = abs(delta_days)
        return TatStatus(
            work_order_id=work_order.id,
            status="DELAYED",
            due_date=due_date_str,
            days_remaining=0,
            days_overdue=overdue_days,
            reason=f"Work order is {overdue_days} day(s) overdue.",
        )

    if delta_days <= 3:
        return TatStatus(
            work_order_id=work_order.id,
            status="AT_RISK",
            due_date=due_date_str,
            days_remaining=delta_days,
            days_overdue=None,
            reason=f"Work order is due within {delta_days} day(s).",
        )

    return TatStatus(
        work_order_id=work_order.id,
        status="ON_TRACK",
        due_date=due_date_str,
        days_remaining=delta_days,
        days_overdue=None,
        reason=f"Work order is on track, due in {delta_days} day(s).",
    )


def get_work_order_tat_status(
    db: Session, *, organization_id: uuid.UUID, work_order_id: uuid.UUID
) -> TatStatus:
    work_order = db.execute(
        select(WorkOrder).where(
            WorkOrder.id == work_order_id,
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if work_order is None:
        raise NotFoundError("Work order not found")

    return calculate_tat_for_work_order(work_order)


def get_fleet_tat_status(db: Session, *, organization_id: uuid.UUID) -> FleetTatSummary:
    res = db.execute(
        select(WorkOrder).where(
            WorkOrder.organization_id == organization_id,
            WorkOrder.deleted_at.is_(None),
        )
    )
    if hasattr(res, "scalars"):
        work_orders = list(res.scalars().all())
    elif hasattr(res, "scalar_one"):
        val = res.scalar_one()
        if isinstance(val, int):
            return FleetTatSummary(
                organization_id=organization_id,
                on_track_count=0,
                at_risk_count=0,
                delayed_count=0,
                unknown_count=val,
                total_work_orders=val,
                reason="No active work orders found for organization." if val == 0 else _FLEET_REASON,
            )
        work_orders = val if isinstance(val, list) else []
    else:
        work_orders = []

    total = len(work_orders)
    if total == 0:
        return FleetTatSummary(
            organization_id=organization_id,
            on_track_count=0,
            at_risk_count=0,
            delayed_count=0,
            unknown_count=0,
            total_work_orders=0,
            reason="No active work orders found for organization.",
        )

    now = datetime.now(UTC)
    on_track_count = 0
    at_risk_count = 0
    delayed_count = 0
    unknown_count = 0

    for wo in work_orders:
        tat = calculate_tat_for_work_order(wo, now=now)
        if tat.status == "ON_TRACK":
            on_track_count += 1
        elif tat.status == "AT_RISK":
            at_risk_count += 1
        elif tat.status == "DELAYED":
            delayed_count += 1
        else:
            unknown_count += 1

    reason = (
        f"Fleet TAT: {on_track_count} on track, {at_risk_count} at risk, "
        f"{delayed_count} delayed, {unknown_count} unknown."
        if unknown_count < total
        else _FLEET_REASON
    )

    return FleetTatSummary(
        organization_id=organization_id,
        on_track_count=on_track_count,
        at_risk_count=at_risk_count,
        delayed_count=delayed_count,
        unknown_count=unknown_count,
        total_work_orders=total,
        reason=reason,
    )
